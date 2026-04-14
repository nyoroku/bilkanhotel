from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.db import transaction
from .models import Sale, WaiterRewardSettings, AuditLog, MenuItem, Order, DeliveryItem, Expense
from accounts.models import User
from core.middleware import get_current_user
from payroll.models import PayrollPeriod
import logging

logger = logging.getLogger(__name__)

# ==============================================================================
# 1. AUDITING SIGNALS
# ==============================================================================

@receiver(pre_save, sender=MenuItem)
def audit_menu_item_pre_save(sender, instance, **kwargs):
    """Capture state before save for MenuItem"""
    if instance.pk:
        try:
            old_instance = MenuItem.objects.get(pk=instance.pk)
            instance._old_selling_price = old_instance.selling_price
            instance._old_stock_quantity = old_instance.stock_quantity
        except MenuItem.DoesNotExist:
            pass

@receiver(post_save, sender=MenuItem)
def audit_menu_item_post_save(sender, instance, created, **kwargs):
    """Log price and stock changes for MenuItem"""
    user = get_current_user()
    
    # 1. Price Change
    if not created and hasattr(instance, '_old_selling_price'):
        if instance.selling_price != instance._old_selling_price:
            AuditLog.objects.create(
                user=user,
                action_type=AuditLog.ActionType.PRICE_CHANGE,
                description=f"Price of {instance.name} changed from {instance._old_selling_price} to {instance.selling_price}",
                content_object=instance,
                data_before={'selling_price': str(instance._old_selling_price)},
                data_after={'selling_price': str(instance.selling_price)},
                variance=instance.selling_price - instance._old_selling_price
            )

    # 2. Manual Stock Adjustment (if not from a delivery which we log separately)
    # This is a bit tricky to distinguish, but we can log all non-zero changes
    if not created and hasattr(instance, '_old_stock_quantity'):
        if instance.stock_quantity != instance._old_stock_quantity:
            # We only log here if it wasn't a standard purchase/delivery (which usually happens via DeliveryItem save)
            # Actually, to be safe and thorough, we log IT ALL.
            AuditLog.objects.create(
                user=user,
                action_type=AuditLog.ActionType.STOCK_ADJUST,
                description=f"Stock of {instance.name} adjusted from {instance._old_stock_quantity} to {instance.stock_quantity}",
                content_object=instance,
                data_before={'stock_quantity': str(instance._old_stock_quantity)},
                data_after={'stock_quantity': str(instance.stock_quantity)},
                variance=instance.stock_quantity - instance._old_stock_quantity
            )

@receiver(post_save, sender=Order)
def audit_order_cancellation(sender, instance, **kwargs):
    """Log order cancellations"""
    if instance.status == Order.Status.CANCELLED:
        user = get_current_user()
        # Find if there was an authorizer
        authorizer = "System"
        if instance.cancellation_requested_by:
            authorizer = instance.cancellation_requested_by.get_full_name()
            
        AuditLog.objects.get_or_create(
            action_type=AuditLog.ActionType.ORDER_CANCEL,
            object_id=instance.id,
            defaults={
                'user': user,
                'description': f"Order #{instance.id} cancelled. Requested/Authorized by: {authorizer}",
                'content_object': instance,
                'data_after': {'status': 'Cancelled', 'total': str(instance.total_amount)}
            }
        )

@receiver(post_save, sender=DeliveryItem)
def audit_delivery_received(sender, instance, created, **kwargs):
    """Log stock intake from deliveries"""
    if created:
        user = get_current_user()
        AuditLog.objects.create(
            user=user,
            action_type=AuditLog.ActionType.DELIVERY,
            description=f"Received {instance.quantity_received} of {instance.menu_item.name} from PO #{instance.delivery.purchase_order.id if instance.delivery.purchase_order else 'N/A'}",
            content_object=instance,
            data_after={'quantity_received': str(instance.quantity_received), 'unit_price': str(instance.unit_price)},
            variance=instance.quantity_received
        )

@receiver(post_save, sender=Expense)
def audit_expense_recorded(sender, instance, created, **kwargs):
    """Log new expenses"""
    if created:
        user = get_current_user()
        AuditLog.objects.create(
            user=user,
            action_type=AuditLog.ActionType.EXPENSE,
            description=f"Expense of {instance.amount} recorded for {instance.category.name}: {instance.description}",
            content_object=instance,
            data_after={'amount': str(instance.amount), 'category': instance.category.name}
        )

@receiver(post_save, sender=PayrollPeriod)
def audit_payroll_status_change(sender, instance, **kwargs):
    """Log payroll approval and payment"""
    user = get_current_user()
    if instance.status in [PayrollPeriod.Status.APPROVED, PayrollPeriod.Status.PAID]:
        AuditLog.objects.create(
            user=user,
            action_type=AuditLog.ActionType.PAYROLL,
            description=f"Payroll '{instance.name}' status changed to {instance.status}",
            content_object=instance,
            data_after={'status': instance.status}
        )

# ==============================================================================
# 2. EXISTING SIGNALS
# ==============================================================================

@receiver(post_save, sender=Sale)
def update_leaderboard_positions(sender, instance, created, **kwargs):
    """
    Automatically recalculate and update leaderboard positions
    whenever a sale is made.

    This ensures real-time dynamic bonuses based on TOTAL accumulated points.
    """
    if not created:
        return

    settings = WaiterRewardSettings.objects.first()
    if not settings or not settings.is_active:
        return

    # Use transaction to ensure atomic updates
    try:
        with transaction.atomic():
            recalculate_all_leaderboard_bonuses()
            logger.info(f"🏆 Leaderboard recalculated after Sale #{instance.id}")
    except Exception as e:
        logger.error(f"❌ Error updating leaderboard after Sale #{instance.id}: {e}")


def recalculate_all_leaderboard_bonuses():
    """
    Recalculate all waiter leaderboard bonuses based on TOTAL POINTS rankings.

    HOW IT WORKS:
    1. Get all waiters ordered by their total points (including current bonus)
    2. Calculate what their ranking SHOULD be based on base points (total - current_bonus)
    3. Adjust bonuses accordingly
    4. Update all waiters atomically

    This ensures the ranking is always based on earned points, not inflated by bonuses.
    """
    settings = WaiterRewardSettings.objects.first()
    if not settings or not settings.is_active:
        logger.info("⚠️ Waiter rewards not active, skipping leaderboard calculation")
        return

    # Get all active waiters with row locking
    waiters = User.objects.filter(
        role='waiter',
        is_active=True
    ).select_for_update()

    # Calculate base points for each waiter (total - current bonus)
    waiter_rankings = []
    for waiter in waiters:
        base_points = waiter.waiter_reward_points - waiter.current_leaderboard_bonus
        waiter_rankings.append({
            'waiter': waiter,
            'base_points': base_points,
            'current_bonus': waiter.current_leaderboard_bonus
        })

    # Sort by base points (descending) to get TRUE rankings
    waiter_rankings.sort(key=lambda x: x['base_points'], reverse=True)

    # Assign new bonuses based on rank
    bonus_assignments = {
        1: settings.gold_bonus_points,
        2: settings.silver_bonus_points,
        3: settings.bronze_bonus_points,
    }

    changes_made = []

    for rank, data in enumerate(waiter_rankings, start=1):
        waiter = data['waiter']
        old_bonus = data['current_bonus']
        new_bonus = bonus_assignments.get(rank, 0)

        if old_bonus != new_bonus:
            # Calculate the change in bonus
            bonus_change = new_bonus - old_bonus

            # Update total points by adjusting for bonus change
            waiter.waiter_reward_points += bonus_change

            # Update the tracked bonus
            waiter.current_leaderboard_bonus = new_bonus

            # Save changes
            waiter.save(update_fields=['waiter_reward_points', 'current_leaderboard_bonus'])

            # Log the change
            change_msg = (
                f"🔄 {waiter.get_full_name()} (Rank #{rank}): "
                f"Bonus {old_bonus} → {new_bonus} (change: {bonus_change:+d}) | "
                f"Total points: {waiter.waiter_reward_points}"
            )
            changes_made.append(change_msg)
            logger.info(change_msg)

    if changes_made:
        logger.info(f"✅ Leaderboard updated. {len(changes_made)} waiter(s) affected")
    else:
        logger.info("✅ Leaderboard checked. No position changes")


def manually_recalculate_leaderboard():
    """
    Helper function to manually trigger leaderboard recalculation.
    Useful for admin actions or scheduled tasks.
    """
    try:
        with transaction.atomic():
            recalculate_all_leaderboard_bonuses()
            return True, "Leaderboard recalculated successfully"
    except Exception as e:
        error_msg = f"Error recalculating leaderboard: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return False, error_msg