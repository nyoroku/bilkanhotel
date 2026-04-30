"""
Telegram bot that links to the existing custom User
and lets staff create purchase orders.
"""

import os
import django

# Let Django bootstrap itself
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "your_project.settings")
django.setup()

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from accounts.models import User                       # your custom user
from pos.models import Supplier, MenuItem, PurchaseOrder, PurchaseOrderItem
from tg_bot.models import TelegramUser                 # one-to-one glue table

# ---------- Conversation states ----------
SELECT_SUPPLIER, SELECT_SECTION, ADD_ITEM, CHOOSE_QTY, CONFIRM = range(5)

# ---------- Helper ----------
def get_user(chat_id: int) -> User | None:
    """
    Return the linked Bilken Hotel user for this chat_id (or None).
    """
    try:
        return TelegramUser.objects.get(chat_id=chat_id).user
    except TelegramUser.DoesNotExist:
        return None

# ---------- /start (for /newpo flow) ----------
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_chat.id)
    if not user:
        await update.message.reply_text(
            "❗ Your Telegram account is not linked to the POS. "
            "Ask an admin to run:\n\n"
            "python manage.py shell\n"
            ">>> from tg_bot.bot import make_link_code\n"
            ">>> make_link_code('EMAIL_HERE')\n\n"
            "then send you the 6-digit code, then run:\n"
            "/link <6-digit-code>"
        )
        return ConversationHandler.END

    # store user object for later states
    ctx.user_data["user"] = user

    # list active suppliers
    suppliers = Supplier.objects.filter(status="Active")
    if not suppliers:
        await update.message.reply_text("❌ No active suppliers.")
        return ConversationHandler.END

    kb = [[s.name] for s in suppliers]
    await update.message.reply_text(
        "📦 Choose supplier:",
        reply_markup={"keyboard": kb, "one_time_keyboard": True}
    )
    return SELECT_SUPPLIER

# ---------- /link ----------
async def link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /link <6-digit-code>
    Binds the Telegram chat to the corresponding User.
    """
    try:
        code = update.message.text.split()[1]
    except IndexError:
        await update.message.reply_text("Usage: /link <6-digit-code>")
        return

    user_id = cache.get(f"link:{code}")
    if not user_id:
        await update.message.reply_text("❌ Code expired or invalid.")
        return

    user = User.objects.get(id=user_id)
    TelegramUser.objects.update_or_create(
        user=user,
        defaults={
            "chat_id": update.effective_chat.id,
            "first_name": update.effective_user.first_name or "",
            "username": update.effective_user.username or "",
        }
    )
    cache.delete(f"link:{code}")  # one-time use
    await update.message.reply_text(
        f"✅ Linked to {user.get_full_name()}! "
        f"You can now create POs with /newpo"
    )

# ---------- PO conversation handlers ----------
async def pick_supplier(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["supplier"] = Supplier.objects.get(name=update.message.text)
    except Supplier.DoesNotExist:
        return SELECT_SUPPLIER

    sections = ["Kitchen", "Bar", "Butchery"]
    kb = [[s] for s in sections]
    await update.message.reply_text(
        "For which section?",
        reply_markup={"keyboard": kb, "one_time_keyboard": True}
    )
    return SELECT_SECTION

async def pick_section(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["section"] = update.message.text
    items = MenuItem.objects.filter(
        is_recipe=False,
        category__module=ctx.user_data["section"]
    )
    kb = [[i.name] for i in items]
    await update.message.reply_text(
        "Choose item:",
        reply_markup={"keyboard": kb, "one_time_keyboard": True}
    )
    return ADD_ITEM

async def pick_item(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["item"] = MenuItem.objects.get(name=update.message.text)
    except MenuItem.DoesNotExist:
        return ADD_ITEM
    await update.message.reply_text(
        "Quantity?",
        reply_markup={"remove_keyboard": True}
    )
    return CHOOSE_QTY

async def pick_qty(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        qty = float(update.message.text)
    except ValueError:
        await update.message.reply_text("Enter a number.")
        return CHOOSE_QTY
    ctx.user_data["qty"] = qty
    await update.message.reply_text("Send 'done' to finish or another item name.")
    return CONFIRM

async def confirm_po(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if text != "done":
        return ADD_ITEM

    user      = ctx.user_data["user"]
    supplier  = ctx.user_data["supplier"]
    section   = ctx.user_data["section"]
    item      = ctx.user_data["item"]
    qty       = ctx.user_data["qty"]

    with transaction.atomic():
        po = PurchaseOrder.objects.create(
            supplier=supplier,
            requested_for_section=section,
            created_by=user,
            notes=f"Created via Telegram by {user.get_full_name()}"
        )
        PurchaseOrderItem.objects.create(
            purchase_order=po,
            menu_item=item,
            quantity_ordered=qty,
            unit_price=item.supplier_cost_price
        )
    await update.message.reply_text(
        f"✅ PO #{po.id} created.",
        reply_markup={"remove_keyboard": True}
    )
    return ConversationHandler.END

# ---------- Admin helper to create a link code ----------
def make_link_code(email: str) -> str:
    """
    Run this once per staff member in Django shell:
    >>> from tg_bot.bot import make_link_code
    >>> make_link_code('staff@example.com')
    """
    import secrets
    user = User.objects.get(email=email)
    code = secrets.token_hex(3)  # 6-char
    cache.set(f"link:{code}", user.id, 300)  # 5 min
    return code

# ---------- Dispatcher ----------
def run_bot():
    app = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN).build()

    # /link command
    app.add_handler(CommandHandler("link", link))

    # /newpo conversation
    conv = ConversationHandler(
        entry_points=[CommandHandler("newpo", start)],
        states={
            SELECT_SUPPLIER: [MessageHandler(filters.TEXT & ~filters.COMMAND, pick_supplier)],
            SELECT_SECTION:  [MessageHandler(filters.TEXT & ~filters.COMMAND, pick_section)],
            ADD_ITEM:        [MessageHandler(filters.TEXT & ~filters.COMMAND, pick_item)],
            CHOOSE_QTY:      [MessageHandler(filters.TEXT & ~filters.COMMAND, pick_qty)],
            CONFIRM:         [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_po)],
        },
        fallbacks=[]
    )
    app.add_handler(conv)
    app.run_polling()


