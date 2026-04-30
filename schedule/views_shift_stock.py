# pos/views_shift_stock.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from decimal import Decimal
from django.contrib.auth.decorators import login_required

from .utils import current_shift_for_user
from .models import ShiftStockTake, Shift
from pos.models import MenuItem, Category

# ---------- OPENING ----------

@login_required
def shift_stock_open(request, section):
    """
    Opening stock page:
    - GET  → read-only preview if already saved, or editable form
    - POST → save / overwrite
    """
    shift = current_shift_for_user(request.user)
    if not shift:
        messages.error(request, "No active shift.")
        return redirect('pos:pos')

    items = MenuItem.objects.filter(is_recipe=False, category__module=section)

    # last closing for reference
    last_closing = {
        st.item_id: st.closing_physical
        for st in ShiftStockTake.objects.filter(
            section=section,
            closing_physical__isnull=False
        ).order_by('-shift__start_datetime', )[:200]
    }

    # existing opening data (may be empty)
    existing = {
        st.item_id: st
        for st in ShiftStockTake.objects.filter(
            shift=shift,
            section=section
        ).select_related('item')
    }

    if request.method == 'POST':
        try:
            with transaction.atomic():
                # upsert each row
                for item in items:
                    phys = Decimal(request.POST.get(f'item_{item.id}', '0'))
                    sys  = item.stock_quantity
                    ShiftStockTake.objects.update_or_create(
                        shift=shift,
                        item=item,
                        section=section,
                        defaults={
                            'opening_physical': phys,
                            'opening_system':   sys,
                            'recorded_by':      request.user
                        }
                    )
                messages.success(request, f"{section} opening stock saved.")
                return redirect('schedule:shift_stock_close', section=section)
        except Exception as e:
            messages.error(request, f"Error saving opening: {e}")

    context = {
        'items': items,
        'shift': shift,
        'section': section,
        'existing': existing,
        'last_closing': last_closing,
    }
    return render(request, 'schedule/shift_stock_open.html', context)
# ---------- CLOSING ----------
@login_required
def shift_stock_close(request, section):
    shift = current_shift_for_user(request.user)
    if not shift:
        messages.error(request, "No active shift.")
        return redirect('pos:pos')

    # ------------------------------------------------------------------
    # 1. Ensure every item has a ShiftStockTake row (create if missing)
    # ------------------------------------------------------------------
    items = MenuItem.objects.filter(is_recipe=False, category__module=section)
    with transaction.atomic():
        for item in items:
            st, created = ShiftStockTake.objects.get_or_create(
                shift=shift,
                item=item,
                section=section,
                defaults={
                    'opening_physical': item.stock_quantity,
                    'opening_system':   item.stock_quantity,
                    'recorded_by':      request.user
                }
            )

    # ------------------------------------------------------------------
    # 2. Fetch rows needing closing count
    # ------------------------------------------------------------------
    stock_takes = ShiftStockTake.objects.filter(
        shift=shift,
        section=section,
        closing_physical__isnull=True
    )

    # ------------------------------------------------------------------
    # 3. Grab last closing for reference
    # ------------------------------------------------------------------
    last_closing = {
        st.item_id: st.closing_physical
        for st in ShiftStockTake.objects.filter(
            section=section,
            closing_physical__isnull=False
        ).order_by('-shift__start_datetime', )[:200]
    }

    # ------------------------------------------------------------------
    # 4. POST
    # ------------------------------------------------------------------
    if request.method == 'POST':
        try:
            with transaction.atomic():
                for st in stock_takes:
                    phys = Decimal(request.POST.get(f'item_{st.item.id}', '0'))
                    st.closing_physical = phys
                    st.closing_system   = st.item.stock_quantity
                    st.save()
            messages.success(request, f"{section} closing stock saved.")
            return redirect('schedule:shift_stock_report', shift_id=shift.id, section=section)
        except Exception as e:
            messages.error(request, f"Error saving closing stock: {e}")

    context = {
        'stock_takes': stock_takes,
        'shift': shift,
        'section': section,
        'last_closing': last_closing,
    }
    return render(request, 'schedule/shift_stock_close.html', context)

# ---------- REPORT ----------
@login_required
def shift_stock_report(request, shift_id, section):
    shift = get_object_or_404(Shift, pk=shift_id)
    stock_takes = ShiftStockTake.objects.filter(shift=shift, section=section)
    context = {'shift': shift, 'stock_takes': stock_takes, 'section': section}
    return render(request, 'schedule/shift_stock_report.html', context)

