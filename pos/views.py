# pos/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.db.models import Prefetch
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, JsonResponse
from decimal import Decimal, InvalidOperation, DivisionByZero,  ROUND_HALF_UP
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from .models import (
    Supplier, Category, MenuItem, StockAlert, PurchaseOrder, PurchaseOrderItem,
    Delivery, DeliveryItem, Order, OrderItem, Table, Customer, Sale,
    CustomerPayment, LoyaltySettings, Coupon, Expense, ExpenseCategory, StockTransfer, WaiterRewardSettings,
    AuditLog
)
from .forms import SupplierForm, CategoryForm, TableForm, MenuItemForm, \
    CustomerForm, PurchaseOrderForm, PurchaseOrderItemFormSet, \
    OrderCreationForm, CustomerPaymentForm, ExpenseForm, \
    ExpenseCategoryForm, RecipeIngredientFormSet
from django.utils import timezone
from django.db.models import Case, When, Count, Q, IntegerField
from django.template.loader import render_to_string
from django.db.models import Sum, F
from django.views import View
from datetime import date
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from django.views.decorators.http import require_http_methods
from .decorators import admin_manager_required
from django.conf import settings
import json
import uuid
from django.views.decorators.http import require_POST
from django.db import IntegrityError
from django.core.exceptions import ValidationError
import math
import traceback
from django.db.models import DecimalField
from django.db.models.functions import Coalesce
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from django.views.decorators.csrf import ensure_csrf_cookie
from accounts.models import User
from schedule.utils import current_shift_for_user
import logging

logger = logging.getLogger(__name__)
# ==============================================================================
# CORE & POS VIEWS
# ==============================================================================


def poss(request):
    """
    Renders the main Point of Sale homepage, which is the table layout.
    """
    tables = Table.objects.filter(is_active=True)
    # This view assumes a template exists at 'pos/homepage.html' to display the tables
    context = {'tables': tables}
    return render(request, 'pos/pos.html', context)

def _base_menu_queryset(request):
    """Shared logic: returns queryset + filtering info."""
    section   = request.GET.get('section', Category.Module.BAR)
    category  = request.GET.get('category', '')
    search    = request.GET.get('search', '').strip()
    page      = request.GET.get('page', 1)

    qs = (
        MenuItem.objects
        .filter(is_active=True,
                selling_price__gt=0,
                category__module=section)
        .select_related('category')
        .order_by('name')
    )

    if category:
        qs = qs.filter(category_id=category)
    if search:
        qs = qs.filter(name__icontains=search)

    paginator = Paginator(qs, getattr(settings, 'MENU_PAGE_SIZE', 10))
    try:
        page_obj = paginator.page(page)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.page(1)

    return {
        'page_obj'         : page_obj,
        'menu_items'       : page_obj.object_list,
        'categories'       : Category.objects.filter(module=section).order_by('name'),
        'active_section'   : section,
        'selected_category': category,
        'search_query'     : search,
    }


def public_menu_landing(request):
    """Public, read-only, mobile-first digital menu."""
    ctx = _base_menu_queryset(request)

    # Hide Butchery and Kitchen tabs
    ctx['sections'] = [s for s in Category.Module.choices if s[0] not in ['Butchery', 'Kitchen']]

    return render(request, 'pos/our-menu.html', ctx)


@admin_manager_required
def admin_dashboard_view(request):
    """
    Renders the admin dashboard with analytics cards AND active stock alerts.
    """
    active_alerts = StockAlert.objects.filter(status=StockAlert.Status.ACTIVE)
    context = {
        'user': request.user,
        'active_alerts': active_alerts,
    }
    # This view assumes a template exists at 'pos/admin_dashboard.html'
    return render(request, 'pos/admin_dashboard.html', context)



@admin_manager_required
def audit_log(request):
    """
    Displays the system audit logs for administrators.
    Supports filtering by user, action type, and date range.
    """
    logs = AuditLog.objects.select_related('user', 'content_type').order_by('-timestamp')

    # Basic Filtering
    user_id = request.GET.get('user')
    action_type = request.GET.get('action_type')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    if user_id:
        logs = logs.filter(user_id=user_id)
    if action_type:
        logs = logs.filter(action_type=action_type)
    if start_date:
        logs = logs.filter(timestamp__date__gte=start_date)
    if end_date:
        logs = logs.filter(timestamp__date__lte=end_date)

    # Variance Highlighting Filter (Bonus)
    if request.GET.get('has_variance'):
        logs = logs.exclude(variance=0).exclude(variance__isnull=True)

    paginator = Paginator(logs, 50)
    page = request.GET.get('page')
    page_obj = paginator.get_page(page)

    context = {
        'page_obj': page_obj,
        'action_types': AuditLog.ActionType.choices,
        'users': User.objects.filter(is_staff=True),
        'selected_user': user_id,
        'selected_action': action_type,
        'start_date': start_date,
        'end_date': end_date,
    }

    if request.htmx:
        return render(request, 'pos/partials/_audit_log_table.html', context)

    return render(request, 'pos/audit_log.html', context)


@admin_manager_required
def dismiss_stock_alert(request, pk):
    alert = get_object_or_404(StockAlert, pk=pk)
    if request.method == 'POST':
        alert.status = StockAlert.Status.DISMISSED
        alert.dismissed_by = request.user
        alert.dismissed_at = timezone.now()
        alert.save()
        messages.success(request, f"Alert for '{alert.menu_item.name}' has been dismissed.")
    return redirect('pos:admin_dashboard')


# ==============================================================================
# MANAGEMENT VIEWS (SUPPLIER, CATEGORY, MENUITEM)
# These views are now fully restored.
# ==============================================================================


@login_required
def supplier_list(request):
    """
    Displays a paginated and filterable list of all Suppliers.
    This view handles both initial page loads and HTMX requests for filtering.
    """
    queryset = Supplier.objects.all().order_by('name')

    # --- Filtering Logic ---
    search_query = request.GET.get('q', '').strip()
    status_query = request.GET.get('status', '')
    supplies_to_query = request.GET.get('supplies_to', '')

    if search_query:
        queryset = queryset.filter(
            Q(name__icontains=search_query) |
            Q(contact_person__icontains=search_query)
        )
    if status_query:
        queryset = queryset.filter(status=status_query)
    if supplies_to_query:
        queryset = queryset.filter(supplies_to=supplies_to_query)

    # --- Pagination ---
    paginator = Paginator(queryset, 15)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # --- Context Data ---
    context = {
        'page_obj': page_obj,
        'statuses': Supplier.Status.choices,
        'sections': Category.Module.choices,
        'search_query': search_query,
        'selected_status': status_query,
        'selected_section': supplies_to_query,
    }

    if request.htmx:
        return render(request, 'pos/partials/_supplier_table.html', context)

    return render(request, 'pos/supplier_list.html', context)


def supplier_add(request):
    if request.method == 'POST':
        form = SupplierForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f"Supplier '{form.cleaned_data['name']}' was added successfully.")
            return redirect('pos:supplier_list')
    else:
        form = SupplierForm()
    context = {'form': form, 'form_title': 'Add New Supplier'}
    return render(request, 'pos/supplier_form.html', context)


def supplier_edit(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == 'POST':
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            form.save()
            messages.success(request, f"Supplier '{supplier.name}' was updated successfully.")
            return redirect('pos:supplier_list')
    else:
        form = SupplierForm(instance=supplier)
    context = {'form': form, 'form_title': f'Edit Supplier: {supplier.name}'}
    return render(request, 'pos/supplier_form.html', context)


def supplier_delete(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == 'POST':
        supplier_name = supplier.name
        supplier.delete()
        messages.success(request, f"Supplier '{supplier_name}' has been deleted.")
        return redirect('pos:supplier_list')
    context = {'supplier': supplier}
    return render(request, 'pos/supplier_confirm_delete.html', context)


@login_required
def category_list_view(request):
    """
    Displays a paginated and filterable list of all Categories.
    This view handles both initial page loads and HTMX requests for filtering.
    """
    queryset = Category.objects.all().order_by('name')

    # --- Filtering Logic ---
    search_query = request.GET.get('q', '').strip()
    section_query = request.GET.get('section', '')

    if search_query:
        queryset = queryset.filter(name__icontains=search_query)

    if section_query:
        queryset = queryset.filter(module=section_query)

    # --- Pagination ---
    paginator = Paginator(queryset, 10)  # 10 categories per page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # --- Context Data ---
    context = {
        'page_obj': page_obj,
        'sections': Category.Module.choices,
        'search_query': search_query,
        'selected_section': section_query,
    }

    # If the request is from HTMX, render only the partial table
    if request.htmx:
        return render(request, 'pos/partials/_category_table.html', context)

    # Otherwise, render the full page
    return render(request, 'pos/category_list.html', context)


@login_required
def category_add(request):
    """
    Handles displaying and processing the form for adding a new Category.
    """
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f"Category '{form.cleaned_data['name']}' was added successfully.")
            return redirect('pos:category_list')
    else:
        form = CategoryForm()

    context = {
        'form': form,
        'form_title': 'Add New Category',
        'back_url': 'pos:category_list' # URL name to go back to the list
    }
    return render(request, 'pos/form_generic.html', context)


@admin_manager_required
def category_edit(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, f"Category '{category.name}' was updated successfully.")
            return redirect('pos:category_list')
    else:
        form = CategoryForm(instance=category)
    context = {'form': form, 'form_title': f'Edit Category: {category.name}'}
    return render(request, 'pos/form_generic.html', context)


@admin_manager_required
def category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if category.menu_items.exists():
        messages.error(request, f"Cannot delete category '{category.name}' because it is used by menu items.")
        return redirect('pos:category_list')
    if request.method == 'POST':
        category_name = category.name
        category.delete()
        messages.success(request, f"Category '{category_name}' has been deleted.")
        return redirect('pos:category_list')
    return render(request, 'pos/delete_form_generic.html', {'item': category})


@login_required
def menu_item_list_view(request):
    """
    Displays a paginated and filterable list of all MenuItems.
    This view handles both initial page loads and HTMX requests for filtering.
    """
    queryset = MenuItem.objects.filter(is_active=True).select_related('category').order_by('name')

    # --- Filtering Logic ---
    search_query = request.GET.get('q', '').strip()
    category_query = request.GET.get('category', '')
    section_query = request.GET.get('section', '')
    low_stock_query = request.GET.get('low_stock', '')

    if search_query:
        queryset = queryset.filter(name__icontains=search_query)

    if category_query:
        queryset = queryset.filter(category_id=category_query)

    if section_query:
        queryset = queryset.filter(category__module=section_query)

    if low_stock_query:
        # Show items where stock is below or equal to the threshold, and threshold is greater than 0
        queryset = queryset.filter(
            low_stock_threshold__gt=0,
            stock_quantity__lte=F('low_stock_threshold')
        )

    # --- Pagination ---
    paginator = Paginator(queryset, 15)  # 15 items per page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # --- Context Data ---
    context = {
        'page_obj': page_obj,
        'all_categories': Category.objects.all().order_by('name'),
        'sections': Category.Module.choices,
        'search_query': search_query,
        'selected_category': category_query,
        'selected_section': section_query,
        'is_low_stock_filtered': low_stock_query,
    }

    # If the request is from HTMX, render only the partial table
    if request.htmx:
        return render(request, 'pos/partials/_menu_item_table.html', context)

    # Otherwise, render the full page
    return render(request, 'pos/menu_item_list.html', context)


@login_required
def menu_item_add(request):
    if request.method == 'POST':
        form = MenuItemForm(request.POST, request.FILES)
        formset = RecipeIngredientFormSet(request.POST)

        if form.is_valid():
            # Defer saving many-to-many and formset until we save the object
            menu_item = form.save(commit=False)
            formset = RecipeIngredientFormSet(request.POST, instance=menu_item)

            if formset.is_valid():
                try:
                    with transaction.atomic():
                        menu_item.save()       # ✅ Must save before using related formsets
                        form.save_m2m()        # ✅ Save any m2m like categories/tags
                        formset.save()         # ✅ Save RecipeIngredient objects
                    messages.success(request, f"Menu item '{menu_item.name}' created successfully.")
                    return redirect('pos:menu_item_list')
                except Exception as e:
                    messages.error(request, f"Error saving menu item: {str(e)}")
            else:
                messages.error(request, "There are errors in the ingredients form.")
        else:
            messages.error(request, "Please correct the errors in the form.")
    else:
        form = MenuItemForm()
        formset = RecipeIngredientFormSet()

    context = {
        'form': form,
        'formset': formset,
        'form_title': 'Create New Menu Item',
    }
    return render(request, 'pos/menu_item_form.html', context)

@login_required
def menu_item_edit(request, pk):
    # First, get the specific menu item we want to edit.
    menu_item = get_object_or_404(MenuItem, pk=pk)

    # Check if the form is being submitted
    if request.method == 'POST':
        # THIS IS THE CRITICAL PART FOR EDITING
        # We must bind the submitted data (request.POST) AND files (request.FILES)
        # to the EXISTING menu_item instance.
        form = MenuItemForm(request.POST, request.FILES, instance=menu_item)

        # We do the same for the formset: bind it to the submitted data AND the instance.
        # This allows Django to correctly identify which ingredients are being updated,
        # which are new, and which are marked for deletion.
        formset = RecipeIngredientFormSet(request.POST, instance=menu_item)

        if form.is_valid() and formset.is_valid():
            # Use a transaction to ensure both the main item and its ingredients
            # are saved together, or not at all if an error occurs.
            with transaction.atomic():
                form.save()
                formset.save()

            messages.success(request, f"Menu item '{menu_item.name}' was updated successfully.")
            return redirect('pos:menu_item_list')
        else:
            # If there are validation errors, we'll print them to the console
            # for debugging, and the template will display them to the user.
            print("Form errors:", form.errors)
            print("Formset errors:", formset.errors)

    # If it's a GET request (just loading the page)
    else:
        # Create a form pre-populated with the existing item's data.
        form = MenuItemForm(instance=menu_item)
        # Create a formset pre-populated with the item's existing ingredients.
        formset = RecipeIngredientFormSet(instance=menu_item)

    context = {
        'form': form,
        'formset': formset,
        'form_title': f'Edit Menu Item: {menu_item.name}'
    }
    return render(request, 'pos/menu_item_form.html', context)


@admin_manager_required
def menu_item_delete(request, pk):
    menu_item = get_object_or_404(MenuItem, pk=pk)
    if MenuItem.objects.filter(source_ingredient=menu_item).exists():
        messages.error(request, f"Cannot delete '{menu_item.name}' as it's a source ingredient for another item.")
        return redirect('pos:menu_item_list')
    if request.method == 'POST':
        item_name = menu_item.name
        menu_item.delete()
        messages.success(request, f"Menu Item '{item_name}' has been deleted.")
        return redirect('pos:menu_item_list')
    return render(request, 'pos/delete_form_generic.html', {'item': menu_item})

# ==============================================================================
# PROCUREMENT & DELIVERY VIEWS
# ==============================================================================


@login_required
def purchase_order_list(request):
    """
    Enhanced purchase order list with filtering, search, and HTMX support
    """
    queryset = PurchaseOrder.objects.select_related('supplier').order_by('-order_date', '-id')

    # Filtering
    status_filter = request.GET.get('status', '')
    supplier_filter = request.GET.get('supplier', '')
    section_filter = request.GET.get('section', '')
    search_query = request.GET.get('q', '').strip()

    if status_filter:
        queryset = queryset.filter(status=status_filter)
    if supplier_filter:
        queryset = queryset.filter(supplier_id=supplier_filter)
    if section_filter:
        queryset = queryset.filter(requested_for_section=section_filter)
    if search_query:
        queryset = queryset.filter(
            Q(id__icontains=search_query) |
            Q(supplier__name__icontains=search_query) |
            Q(notes__icontains=search_query)
        )

    # Pagination
    paginator = Paginator(queryset, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'statuses': PurchaseOrder.Status.choices,
        'suppliers': Supplier.objects.all(),
        'sections': PurchaseOrder.Section.choices,
        'selected_status': status_filter,
        'selected_supplier': supplier_filter,
        'selected_section': section_filter,
        'search_query': search_query,
    }

    if request.htmx:
        return render(request, 'pos/partials/_purchase_order_table.html', context)

    return render(request, 'pos/purchase_order_list.html', context)


@login_required
@transaction.atomic
def purchase_order_create(request):
    """
    Enhanced purchase order creation with better form handling
    """
    if request.method == 'POST':
        form = PurchaseOrderForm(request.POST)
        formset = PurchaseOrderItemFormSet(request.POST, prefix='items')

        if form.is_valid() and formset.is_valid():
            po = form.save(commit=False)
            po.created_by = request.user

            # Calculate total cost
            total_cost = sum(
                item.cleaned_data.get('quantity_ordered', 0) *
                item.cleaned_data.get('unit_price', 0)
                for item in formset
                if item.cleaned_data and not item.cleaned_data.get('DELETE', False)
            )

            po.total_cost = total_cost
            po.save()
            formset.instance = po
            formset.save()

            messages.success(request, f'Purchase Order #{po.id} created successfully.')
            return redirect('pos:purchase_order_detail', pk=po.id)
    else:
        form = PurchaseOrderForm(initial={
            'requested_for_section': PurchaseOrder.Section.BAR,
            'order_date': timezone.now().date()
        })
        formset = PurchaseOrderItemFormSet(prefix='items')

    context = {
        'form': form,
        'formset': formset,
        'form_title': 'Create Purchase Order',
        'menu_items': MenuItem.objects.filter(is_recipe=False).order_by('name'),
    }
    return render(request, 'pos/purchase_order_form.html', context)


@login_required
@transaction.atomic
def purchase_order_edit(request, pk):
    """
    Edit existing purchase order with proper versioning
    """
    po = get_object_or_404(PurchaseOrder, pk=pk)

    if request.method == 'POST':
        form = PurchaseOrderForm(request.POST, instance=po)
        formset = PurchaseOrderItemFormSet(request.POST, prefix='items', instance=po)

        if form.is_valid() and formset.is_valid():
            po = form.save(commit=False)

            # Recalculate total cost
            total_cost = sum(
                item.cleaned_data.get('quantity_ordered', 0) *
                item.cleaned_data.get('unit_price', 0)
                for item in formset
                if item.cleaned_data and not item.cleaned_data.get('DELETE', False)
            )

            po.total_cost = total_cost
            po.save()
            formset.save()

            messages.success(request, f'Purchase Order #{po.id} updated successfully.')
            return redirect('pos:purchase_order_detail', pk=po.id)
    else:
        form = PurchaseOrderForm(instance=po)
        formset = PurchaseOrderItemFormSet(prefix='items', instance=po)

    context = {
        'form': form,
        'formset': formset,
        'form_title': f'Edit Purchase Order #{po.id}',
        'menu_items': MenuItem.objects.filter(is_recipe=False).order_by('name'),
        'po': po,
    }
    return render(request, 'pos/purchase_order_form.html', context)

@login_required
def purchase_order_detail(request, pk):
    po = get_object_or_404(PurchaseOrder.objects.prefetch_related('items__menu_item'), pk=pk)
    return render(request, 'pos/purchase_order_detail.html', {'po': po})


@login_required # Or @admin_manager_required
def receive_delivery_from_po(request, po_id):
    po = get_object_or_404(PurchaseOrder.objects.prefetch_related('items__menu_item'), pk=po_id)

    if request.method == 'POST':
        delivery_note = request.POST.get('delivery_note', '').strip()

        try:
            with transaction.atomic():
                # Create the delivery record, now correctly including the supplier
                delivery = Delivery.objects.create(
                    purchase_order=po,
                    supplier=po.supplier, # This was missing before
                    received_by=request.user,
                    delivery_note=delivery_note
                )

                items_were_received = False

                for item in po.items.all():
                    # Get the quantity received from the form for this specific item
                    received_qty_str = request.POST.get(f'item_{item.id}_received_qty', '0')
                    received_qty = Decimal(received_qty_str) if received_qty_str else Decimal('0')

                    if received_qty > 0:
                        items_were_received = True

                        # 1. Create the DeliveryItem record to log what came in this delivery.
                        #    This will trigger the stock update in your model's save() method.
                        DeliveryItem.objects.create(
                            delivery=delivery,
                            menu_item=item.menu_item,
                            quantity_received=received_qty,
                            unit_price=item.unit_price
                        )

                        # 2. CRITICAL FIX: Update the original PurchaseOrderItem
                        #    to reflect the new total quantity received for that line item.
                        item.quantity_received += received_qty
                        item.save() # This save will trigger the PO status update

                if not items_were_received:
                    # If the user submitted the form without entering any quantities,
                    # delete the empty Delivery record we just created.
                    delivery.delete()
                    messages.warning(request, "No items were marked as received.")
                    return redirect('pos:purchase_order_detail', pk=po.id)

                # The po.update_status() is now automatically called by item.save()
                # so we don't need to call it again.

                messages.success(request, "Delivery recorded successfully!")
                return redirect('pos:purchase_order_detail', pk=po.id)

        except Exception as e:
            messages.error(request, f"Error recording delivery: {str(e)}")
            return redirect('pos:purchase_order_detail', pk=po.id)

    return render(request, 'pos/receive_delivery.html', {'po': po})
# ==============================================================================
# REPORTING VIEWS
# ==============================================================================

# This is the helper function we corrected previously. It must also be in your views.py file.
def _prepare_variance_data(purchase_orders):
    """
    Prepares data for variance reports using the efficient quantity_received field.
    """
    variance_data = []
    po_items = PurchaseOrderItem.objects.filter(
        purchase_order__in=purchase_orders
    ).select_related('menu_item', 'purchase_order__supplier')

    for item in po_items:
        total_received = item.quantity_received
        quantity_variance = total_received - item.quantity_ordered

        variance_data.append({
            'po': item.purchase_order,
            'po_item': item,
            'total_received': total_received,
            'quantity_variance': quantity_variance,
        })

    return variance_data


# NOTE: You will need an @admin_manager_required decorator for production
# from .decorators import admin_manager_required

# @admin_manager_required
@login_required
def po_variance_report_all(request):
    """
    Displays the variance report for ALL fully received purchase orders.
    Handles HTMX requests for dynamic date filtering.
    """
    # Get date range from GET parameters, with a default of the last 30 days
    end_date_str = request.GET.get('end_date')
    start_date_str = request.GET.get('start_date')

    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else timezone.now().date()
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else end_date - timedelta(
        days=30)

    # Fetch all purchase orders that were marked as received within the date range
    completed_pos = PurchaseOrder.objects.filter(
        status__in=[PurchaseOrder.Status.PARTIALLY_RECEIVED, PurchaseOrder.Status.FULLY_RECEIVED],
        order_date__range=[start_date, end_date]
    ).order_by('-order_date')

    # Prepare the data using the helper function
    variance_data = _prepare_variance_data(completed_pos)

    context = {
        'report_title': 'Overall Purchase Order Variance Report',
        'variance_data': variance_data,
        'start_date': start_date,
        'end_date': end_date,
    }

    # If the request is from HTMX (i.e., a filter was applied),
    # render only the partial table.
    if request.htmx:
        return render(request, 'pos/partials/_po_variance_report_table.html', context)

    # Otherwise, render the full page shell.
    return render(request, 'pos/po_variance_report.html', context)


# @admin_manager_required
@login_required
def po_variance_report_supplier(request, pk):
    """
    Displays the variance report for a SINGLE supplier.
    Handles HTMX requests for dynamic date filtering.
    """
    supplier = get_object_or_404(Supplier, pk=pk)

    # Get date range from GET parameters, with a default of the last 30 days
    end_date_str = request.GET.get('end_date')
    start_date_str = request.GET.get('start_date')

    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else timezone.now().date()
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else end_date - timedelta(
        days=30)

    # Fetch purchase orders for this specific supplier within the date range
    completed_pos = PurchaseOrder.objects.filter(
        supplier=supplier,
        status__in=[PurchaseOrder.Status.PARTIALLY_RECEIVED, PurchaseOrder.Status.FULLY_RECEIVED],
        order_date__range=[start_date, end_date]
    ).order_by('-order_date')

    # Prepare the data using the helper function
    variance_data = _prepare_variance_data(completed_pos)

    context = {
        'report_title': f'PO Variance Report for: {supplier.name}',
        'variance_data': variance_data,
        'supplier': supplier,
        'start_date': start_date,
        'end_date': end_date,
    }

    # If the request is from HTMX, render only the partial table.
    if request.htmx:
        return render(request, 'pos/partials/_po_variance_report_table.html', context)

    # Otherwise, render the full page shell.
    return render(request, 'pos/po_variance_report.html', context)


# ==============================================================================
# HELPER FUNCTION
# ==============================================================================

def get_table_session(request):
    """
    Initializes or retrieves the session for the current order, which contains
    separate carts for Kitchen and Bar.
    """
    if 'table_session' not in request.session:
        request.session['table_session'] = {
            'kitchen_cart': {'items': {}, 'total': 0.0},
            'bar_cart': {'items': {}, 'total': 0.0},
        }
    return request.session['table_session']


# ==============================================================================
# WAITER WORKFLOW (Dashboard, Order Detail)
# ==============================================================================
def get_waiter_leaderboard_data():
    """
    Calculate leaderboard rankings based on BASE POINTS (total points minus current bonus).
    This ensures rankings aren't inflated by the position bonuses themselves.
    Returns list of dicts with waiter data and rankings.
    """
    from accounts.models import User

    # Get settings
    settings = WaiterRewardSettings.objects.first()
    if not settings or not settings.is_active:
        return []

    # Get all active waiters
    waiters = User.objects.filter(
        role='waiter',
        is_active=True
    )

    # Calculate base points and create ranking list
    waiter_data_list = []
    for waiter in waiters:
        current_total = waiter.waiter_reward_points
        current_bonus = waiter.current_leaderboard_bonus

        # Base points = total points - current bonus
        base_points = current_total - current_bonus

        waiter_data_list.append({
            'waiter': waiter,
            'waiter_id': waiter.id,
            'waiter_name': waiter.get_full_name(),
            'profile_image': waiter.profile_image.url if waiter.profile_image else None,
            'base_points': base_points,
            'current_bonus': current_bonus,
            'current_total': current_total,
        })

    # Sort by BASE POINTS (descending) - this is the true ranking
    waiter_data_list.sort(key=lambda x: x['base_points'], reverse=True)

    # Assign ranks and calculate correct totals with new bonuses
    leaderboard_data = []
    for idx, data in enumerate(waiter_data_list, start=1):
        data['rank'] = idx

        # Assign medal and display bonus based on current rank
        if idx == 1:
            data['medal'] = 'gold'
            data['medal_icon'] = '🥇'
            data['display_bonus'] = settings.gold_bonus_points
        elif idx == 2:
            data['medal'] = 'silver'
            data['medal_icon'] = '🥈'
            data['display_bonus'] = settings.silver_bonus_points
        elif idx == 3:
            data['medal'] = 'bronze'
            data['medal_icon'] = '🥉'
            data['display_bonus'] = settings.bronze_bonus_points
        else:
            data['medal'] = None
            data['medal_icon'] = ''
            data['display_bonus'] = 0

        # ✅ Calculate the CORRECT total: base_points + display_bonus
        data['display_total'] = data['base_points'] + data['display_bonus']

        leaderboard_data.append(data)

    return leaderboard_data

@login_required
def waiter_dashboard(request):
    """
    Shift-scoped waiter dashboard with live leaderboard.
    KPIs & orders are filtered to the exact datetime range of the current shift.
    Leaderboard shows real-time rankings with dynamic bonuses.
    """
    shift = current_shift_for_user(request.user)
    if not shift:
        return render(request, 'schedule/no_shift.html', {})

    # KPIs scoped to the exact datetime range
    shift_start = shift.start_datetime
    shift_end = shift.end_datetime

    sales_in_shift = Sale.objects.filter(
        processed_at__gte=shift_start,
        processed_at__lte=shift_end,
        order__waiter=request.user
    ).aggregate(t=Sum('amount_paid'))['t'] or 0

    orders_in_shift = Order.objects.filter(
        created_at__gte=shift_start,
        created_at__lte=shift_end,
        waiter=request.user
    )

    kpi_stats = {
        'total_sales_today': sales_in_shift,
        'sales_count_today': orders_in_shift.count(),
        'my_tables_count': orders_in_shift.values('table').distinct().count(),
        'attention_count': orders_in_shift.filter(status='Ready').count(),
    }

    # Original table grid, scoped to orders inside this shift
    open_orders_prefetch = Prefetch(
        'orders',
        queryset=orders_in_shift.filter(status__in=['Pending', 'Ready'])
        .prefetch_related('items__menu_item'),
        to_attr='open_orders'
    )

    tables = Table.objects.filter(is_active=True).prefetch_related(open_orders_prefetch).order_by('table_number')

    for table in tables:
        table.open_orders = list(table.open_orders)
        table.has_my_orders = bool(table.open_orders)
        table.is_occupied = table.has_my_orders
        table.total_open_orders = len(table.open_orders)
        table.needs_attention = any(o.status == 'Ready' for o in table.open_orders)

    # NEW: Get leaderboard data (using current week as period)
    leaderboard_data = get_waiter_leaderboard_data()

    # Find current user's position in the leaderboard
    current_waiter_rank = None
    for item in leaderboard_data:
        if item['waiter_id'] == request.user.id:
            current_waiter_rank = item
            break

    # Get top 3 for display
    top_three = leaderboard_data[:3]

    context = {
        'shift': shift,
        'kpi_stats': kpi_stats,
        'tables': tables,
        'waiter_points': request.user.waiter_reward_points,

        # NEW: Leaderboard data
        'leaderboard_top_three': top_three,
        'current_waiter_rank': current_waiter_rank,
        'leaderboard_settings': WaiterRewardSettings.objects.first(),
        'all_leaderboard_data': leaderboard_data,  # Full list for debugging/extended view
    }
    return render(request, 'pos/waiter_dashboard.html', context)


# @waiter_required
@login_required
def table_detail_view(request, table_id):
    """
    The new central hub for a single table. Shows all open orders on the table
    created by the current waiter and provides actions like adding orders, printing, and paying.
    """
    table = get_object_or_404(Table, pk=table_id)
    open_statuses = [Order.Status.PENDING, Order.Status.READY]

    # Get all open orders for this table that belong to the current waiter
    open_orders = table.orders.filter(
        status__in=open_statuses,
        waiter=request.user  # Only show orders created by the current waiter
    ).prefetch_related('items__menu_item', 'waiter').order_by('created_at')

    # For each order, calculate its age
    for order in open_orders:
        order.age = timezone.now() - order.created_at

    context = {
        'table': table,
        'open_orders': open_orders,
    }
    return render(request, 'pos/table_detail.html', context)

@login_required
def print_consolidated_bill(request):
    """
    Generates a single, long, printable receipt that combines
    all items from multiple selected orders for a table.
    """
    order_ids_str = request.GET.get('order_ids', '')
    if not order_ids_str:
        return HttpResponse("No order IDs provided.", status=400)

    order_ids = order_ids_str.split(',')

    orders = Order.objects.filter(id__in=order_ids).prefetch_related('items__menu_item', 'waiter')
    if not orders.exists():
        return HttpResponse("Orders not found.", status=404)

    grand_total = sum(order.total_amount for order in orders)
    table_name = orders.first().table.table_number

    context = {
        'orders': orders,
        'grand_total': grand_total,
        'table_name': table_name,
        'print_timestamp': timezone.now(),
    }
    return render(request, 'pos/print_consolidated_bill.html', context)
# @waiter_required
@login_required
def create_order_for_table(request, table_id):
    """
    Starts the order creation process for a specific, pre-selected table.
    It reuses the main create_order.html template.
    """
    table = get_object_or_404(Table, pk=table_id)
    walk_in_customer, _ = Customer.objects.get_or_create(pk=1, defaults={'name': 'Walking In'})

    form = OrderCreationForm(initial={'table': table, 'customer': walk_in_customer})

    # Only show Bar items as requested
    sections_to_display = [(Category.Module.BAR, Category.Module.BAR.label)]
    active_module = Category.Module.BAR
    initial_categories = Category.objects.filter(module=active_module).order_by('name')
    initial_menu_items = MenuItem.objects.filter(is_active=True, category__module=active_module,
                                                 selling_price__gt=0).order_by('name')

    context = {
        'form': form,
        'sections': sections_to_display,
        'kitchen_cart': get_table_session(request)['kitchen_cart'],
        'bar_cart': get_table_session(request)['bar_cart'],
        'active_module': active_module,
        'default_customer_name': walk_in_customer.name,
        'initial_categories': initial_categories,
        'initial_menu_items': initial_menu_items,
        'selected_table': table,
    }
    return render(request, 'pos/create_order.html', context)


@login_required
def print_kitchen_docket(request, order_id):
    """
    Print kitchen docket containing only kitchen items from the order.
    """
    order = get_object_or_404(Order, pk=order_id)

    # Filter only kitchen items
    kitchen_items = order.items.filter(
        menu_item__category__module=Category.Module.KITCHEN
    ).select_related('menu_item', 'menu_item__category')

    # If no kitchen items, return empty response or message
    if not kitchen_items.exists():
        return HttpResponse("No kitchen items in this order", content_type="text/plain")

    context = {
        'order': order,
        'items': kitchen_items,
        'docket_type': 'KITCHEN',
        'print_time': timezone.now(),
        'total_items': kitchen_items.count(),
    }

    return render(request, 'pos/print/kitchen_docket.html', context)


@login_required
def print_bar_docket(request, order_id):
    """
    Print bar docket containing only bar items from the order.
    """
    order = get_object_or_404(Order, pk=order_id)

    # Filter only bar items
    bar_items = order.items.filter(
        menu_item__category__module=Category.Module.BAR
    ).select_related('menu_item', 'menu_item__category')

    # If no bar items, return empty response or message
    if not bar_items.exists():
        return HttpResponse("No bar items in this order", content_type="text/plain")

    context = {
        'order': order,
        'items': bar_items,
        'docket_type': 'BAR',
        'print_time': timezone.now(),
        'total_items': bar_items.count(),
    }

    return render(request, 'pos/print/bar_docket.html', context)
# @waiter_required
@login_required
def waiter_order_detail_view(request, order_id):
    """
    Displays the details of a specific order for management (removing items, canceling).
    """
    order = get_object_or_404(
        Order.objects.select_related('table', 'customer').prefetch_related('items__menu_item'),
        pk=order_id,
        waiter=request.user  # Security check
    )
    return render(request, 'pos/waiter_order_detail.html', {'order': order})


# --- HTMX Views for Order Management ---


@login_required
@require_POST
def htmx_remove_item_from_order(request, item_id):
    order_item = get_object_or_404(
        OrderItem.objects.select_related('order__table', 'menu_item'),
        pk=item_id,
        order__waiter=request.user
    )
    order = order_item.order
    table_id = order.table.id

    # Business rule: allow removal only if not a recipe item and order is ready
    can_remove = not order_item.menu_item.is_recipe
    if order.status == Order.Status.READY and not can_remove:
        messages.error(request, "Cannot remove a prepared food item from a 'Ready' order.")
        response = HttpResponse()
        response['HX-Redirect'] = reverse('pos:waiter_order_detail', args=[order.id])
        return response

    order_item.delete()

    # ✅ FIXED: Handle custom amounts like in finalize_orders
    new_subtotal = 0
    for item in order.items.all():
        # Detect custom amount items (fractional quantity for weight-based items)
        if item.menu_item.sell_by_weight:
            # Custom amount - use price_at_sale directly
            new_subtotal += item.price_at_sale
        else:
            # Regular item - calculate normally
            new_subtotal += item.quantity * item.price_at_sale

    order.subtotal = new_subtotal
    order.save(update_fields=['subtotal'])

    response = HttpResponse()

    # If order is now empty, auto-cancel and redirect to dashboard
    if not order.items.exists():
        order.status = Order.Status.CANCELLED
        order.save(update_fields=['status'])
        messages.info(request, f"Order #{order.id} was empty and has been cancelled.")
        response['HX-Redirect'] = reverse('pos:table_detail', args=[table_id])
    else:
        messages.success(request, f"Item removed from Order #{order.id}.")
        response['HX-Redirect'] = reverse('pos:table_detail', args=[table_id])

    return response

@login_required
def htmx_cancel_order(request, order_id):
    """ Cancels an entire order via HTMX. """
    order = get_object_or_404(Order.objects.select_related('table').prefetch_related('items__menu_item'), pk=order_id,
                              waiter=request.user)

    can_cancel_ready = not order.items.filter(menu_item__is_recipe=True).exists()

    if order.status == Order.Status.READY and not can_cancel_ready:
        messages.error(request, "Cannot cancel a prepared food order.")
        return redirect('pos:waiter_order_detail', order_id=order.id)

    table_id = order.table.id
    order.delete()
    messages.success(request, f"Order #{order.id} has been successfully cancelled.")

    response = HttpResponse()
    response['HX-Redirect'] = reverse('pos:table_detail', args=[table_id])
    return response


@login_required
def waiter_order_detail(request, order_id):
    """
    Shows the detailed view of a single order for the waiter to track item statuses.
    """
    order = get_object_or_404(
        Order.objects.prefetch_related('items__menu_item__category'),
        pk=order_id,
        waiter=request.user  # Security check
    )
    context = {'order': order}
    return render(request, 'pos/waiter_order_detail.html', context)


# ==============================================================================
# DYNAMIC ORDER CREATION
# ==============================================================================


@login_required
def create_order(request):
    """
    Renders the main ordering application.
    This view now correctly provides all necessary initial data for the template.
    """
    walk_in_customer, _ = Customer.objects.get_or_create(pk=1, defaults={'name': 'Walking In'})
    form = OrderCreationForm(initial={'customer': walk_in_customer})

    # Only show Bar items as requested
    sections_to_display = [
        (Category.Module.BAR, Category.Module.BAR.label),
    ]

    active_module = Category.Module.BAR

    # Fetch initial data for the default "Kitchen" tab
    initial_categories = Category.objects.filter(module=active_module).order_by('name')
    initial_menu_items = MenuItem.objects.filter(
        is_active=True, category__module=active_module, selling_price__gt=0
    ).order_by('name')

    context = {
        'form': form,
        'sections': sections_to_display,
        'kitchen_cart': get_table_session(request)['kitchen_cart'],
        'bar_cart': get_table_session(request)['bar_cart'],
        'active_module': active_module,
        'default_customer_name': walk_in_customer.name,
        # Pass initial data for the first page load
        'initial_categories': initial_categories,
        'initial_menu_items': initial_menu_items,
    }
    return render(request, 'pos/create_order.html', context)


@login_required
@require_POST
def finalize_orders(request):
    """
    Finalizes the current order session.
    Can either CREATE a new order or ADD items to an existing one.
    Uses cart total directly to avoid rounding issues.
    Redirects to table_detail.
    """
    if request.method != 'POST':
        return redirect('pos:waiter_dashboard')

    existing_order_id = request.POST.get('existing_order_id')
    table_session = get_table_session(request)
    form = OrderCreationForm(request.POST)
    if not form.is_valid():
        messages.error(request, "There was an error with the form submission.")
        return redirect('pos:waiter_dashboard')

    try:
        with transaction.atomic():
            if existing_order_id:
                # Adding items to existing order
                order = get_object_or_404(Order, pk=existing_order_id, waiter=request.user)
                order_section = order.items.first().menu_item.category.module
                cart_name = 'kitchen_cart' if order_section == 'Kitchen' else 'bar_cart'
                cart = table_session.get(cart_name, {})

                if not cart.get('items'):
                    messages.warning(request, "No new items were added.")
                    return redirect('pos:table_detail', table_id=order.table.id)

                for item_id, data in cart['items'].items():
                    menu_item = get_object_or_404(MenuItem, id=item_id)
                    quantity = Decimal(str(data['quantity']))
                    price_at_sale = menu_item.selling_price

                    # Create OrderItem
                    order_item = OrderItem.objects.create(
                        order=order,
                        menu_item=menu_item,
                        quantity=quantity,
                        price_at_sale=price_at_sale,
                        # ✅ FIXED: Always set subtotal from session cart data
                        subtotal=Decimal(str(data['price']))  # This contains the correct total
                    )

                # ✅ Use cart total directly — no recalculation
                cart_total = Decimal(str(cart.get('total', 0))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                order.subtotal = (order.subtotal + cart_total).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                order.save()

                table_id_for_redirect = order.table.id
                messages.success(request, f"New items added to Order #{order.id}.")

            else:
                # Creating new order
                customer = form.cleaned_data['customer']
                table = form.cleaned_data.get('table')

                kitchen_cart = table_session.get('kitchen_cart', {})
                bar_cart = table_session.get('bar_cart', {})

                if kitchen_cart.get('items'):
                    kitchen_total = Decimal(str(kitchen_cart.get('total', 0))).quantize(Decimal('0.01'),
                                                                                        rounding=ROUND_HALF_UP)
                    k_order = Order.objects.create(
                        waiter=request.user,
                        customer=customer,
                        table=table,
                        subtotal=kitchen_total
                    )
                    for item_id, data in kitchen_cart['items'].items():
                        menu_item = get_object_or_404(MenuItem, id=item_id)
                        quantity = Decimal(str(data['quantity']))
                        price_at_sale = menu_item.selling_price

                        # ✅ FIXED: If custom amount exists, use data['price'] as subtotal, otherwise calculate normally
                        if data.get('custom_amount'):
                            subtotal = Decimal(str(data['price']))  # Use the stored price directly
                        else:
                            subtotal = quantity * price_at_sale  # Calculate normally

                        OrderItem.objects.create(
                            order=k_order,
                            menu_item=menu_item,
                            quantity=quantity,
                            price_at_sale=Decimal(str(data['custom_amount'])) if data.get(
                                'custom_amount') else price_at_sale,
                            subtotal=subtotal
                        )

                if bar_cart.get('items'):
                    bar_total = Decimal(str(bar_cart.get('total', 0))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    b_order = Order.objects.create(
                        waiter=request.user,
                        customer=customer,
                        table=table,
                        subtotal=bar_total
                    )
                    for item_id, data in bar_cart['items'].items():
                        menu_item = get_object_or_404(MenuItem, id=item_id)
                        quantity = Decimal(str(data['quantity']))
                        price_at_sale = menu_item.selling_price

                        # ✅ FIXED: If custom amount exists, use data['price'] as subtotal, otherwise calculate normally
                        if data.get('custom_amount'):
                            subtotal = Decimal(str(data['custom_amount']))  # Use the stored price directly
                        else:
                            subtotal = quantity * price_at_sale  # Calculate normally

                        OrderItem.objects.create(
                            order=b_order,
                            menu_item=menu_item,
                            quantity=quantity,
                            price_at_sale=price_at_sale,
                            subtotal=subtotal
                        )

                if table:
                    table.status = Table.Status.OCCUPIED
                    table.save()
                table_id_for_redirect = table.id if table else None
                messages.success(request, "New order(s) created successfully.")

                # Clear session
                del request.session['table_session']
                request.session.modified = True

            # ✅ Redirect to table detail
            return redirect('pos:table_detail', table_id=table_id_for_redirect)

    except Exception as e:
        messages.error(request, f"An error occurred while creating the order: {e}")
        return redirect('pos:waiter_dashboard')
# ==============================================================================
# HTMX ENDPOINTS
# ==============================================================================


from django.http import HttpResponseBadRequest

@login_required
def htmx_menu_content(request):
    # 1) Reject non-HTMX requests immediately
    if request.headers.get('HX-Request') != 'true':
        return HttpResponseBadRequest("Invalid HTMX request")

    # 2) Your existing logic (unchanged)
    section_query   = request.GET.get('section', Category.Module.KITCHEN)
    category_query  = request.GET.get('category', '')
    search_query    = request.GET.get('search', '').strip()   # ← note: use 'search' not 'q'
    page_number     = request.GET.get('page', 1)

    menu_items = (
        MenuItem.objects
        .filter(is_active=True,
                selling_price__gt=0,
                category__module=section_query)
        .select_related('category')
        .order_by('name')
    )

    if category_query:
        menu_items = menu_items.filter(category_id=category_query)

    if search_query:
        menu_items = menu_items.filter(name__icontains=search_query)

    paginator = Paginator(menu_items, getattr(settings, 'MENU_PAGE_SIZE', 10))
    page_obj  = paginator.get_page(page_number)

    context = {
        'page_obj'         : page_obj,
        'menu_items'       : page_obj.object_list,
        'categories'       : Category.objects.filter(module=section_query).order_by('name'),
        'active_section'   : section_query,
        'selected_category': category_query,
        'search_query'     : search_query,
    }
    return render(request, 'pos/partials/_menu_content.html', context)
# --- ADD OR REPLACE THE CART MANAGEMENT VIEWS ---


@login_required
@require_POST
def htmx_add_order_item(request):
    """
    Adds an item to the session cart (kitchen or bar).
    Handles both standard quantity and custom amount (weight-based) items.
    Ensures the entered amount is preserved exactly.
    """
    if request.method != 'POST':
        return HttpResponse(status=405)

    try:
        menu_item_id = request.POST.get('menu_item_id')
        module = request.POST.get('module')
        quantity_str = request.POST.get('quantity', '1')
        custom_amount_str = request.POST.get('custom_amount')  # e.g., "400"

        if not menu_item_id:
            return _render_error_response(request, "Menu item ID is required.")
        if not module:
            return _render_error_response(request, "Module is required.")

        menu_item = get_object_or_404(MenuItem, id=menu_item_id)

        if not menu_item.is_active:
            return _render_error_response(request, f"'{menu_item.name}' is currently unavailable.")

        selling_price = menu_item.selling_price  # Decimal

        # Handle custom amount: user enters total KES (e.g., 400)
        if custom_amount_str:
            try:
                custom_amount = Decimal(custom_amount_str)
                if custom_amount <= 0:
                    return _render_error_response(request, "Amount must be greater than 0.")

                # Calculate quantity for stock: 400 / 700 = 0.571 kg
                quantity = (custom_amount / selling_price).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)

                # ✅ Use custom_amount as the final line total for THIS addition
                line_total = custom_amount

            except (InvalidOperation, DivisionByZero):
                return _render_error_response(request, "Invalid amount entered.")
        else:
            try:
                quantity = Decimal(quantity_str)
                if quantity <= 0:
                    return _render_error_response(request, "Quantity must be greater than 0.")
            except InvalidOperation:
                return _render_error_response(request, "Invalid quantity.")
            line_total = quantity * selling_price

        # Stock check
        if not menu_item.is_recipe:
            if menu_item.stock_quantity is None:
                return _render_error_response(request, f"'{menu_item.name}' stock not tracked.")
            if menu_item.stock_quantity <= 0:
                return _render_error_response(request, f"'{menu_item.name}' is out of stock.")
            if menu_item.stock_quantity < quantity:
                return _render_error_response(request, f"Not enough stock for {menu_item.name}.")

        # Add to session cart
        table_session = get_table_session(request)
        cart_name = 'kitchen_cart' if module == 'Kitchen' else 'bar_cart'
        session_cart = table_session.setdefault(cart_name, {'items': {}, 'total': 0.0})

        item_id_str = str(menu_item.id)
        item_data = session_cart['items'].get(item_id_str, {})
        new_quantity = item_data.get('quantity', 0) + float(quantity)

        # Final stock check
        if not menu_item.is_recipe and menu_item.stock_quantity < new_quantity:
            return _render_error_response(request, f"Not enough stock to add another '{menu_item.name}'.")

        # ✅ Calculate the TOTAL price for ALL quantities of this item
        if custom_amount_str:
            # For custom amounts, add the new custom amount to existing price
            existing_price = Decimal(str(item_data.get('price', 0)))
            total_item_price = existing_price + custom_amount
        else:
            # For regular items, multiply total quantity by unit price
            total_item_price = Decimal(str(new_quantity)) * selling_price

        # ✅ FIXED: Store prices as strings to avoid float precision issues
        session_cart['items'][item_id_str] = {
            'name': menu_item.name,
            'quantity': new_quantity,
            'price': str(total_item_price.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),  # ← Store as string
            'unit_price': str(selling_price.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),  # ← Store as string
            'custom_amount': custom_amount_str if custom_amount_str else None,  # ← Keep as string
        }

        # ✅ Recalculate cart total as sum of all item prices
        total = sum(Decimal(v['price']) for v in session_cart['items'].values())
        session_cart['total'] = str(total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))  # ← Store as string

        request.session.modified = True

        # ✅ Return updated cart with modal close trigger
        if request.htmx:
            response = render(request, 'pos/partials/_order_summary.html', {
                'cart': session_cart,
                'module': module
            })
            # Trigger modal close on successful addition
            response['HX-Trigger'] = 'close-modal'
            return response
        else:
            # Fallback for non-HTMX requests
            return render(request, 'pos/partials/_order_summary.html', {
                'cart': session_cart,
                'module': module
            })

    except Exception as e:
        logger.error(f"Error in htmx_add_order_item: {str(e)}", exc_info=True)
        return _render_error_response(request, "A system error occurred. Please try again.")


@login_required
def htmx_item_add_modal(request, item_id):
    """
    Returns a modal form for items sold by weight (e.g., meat).
    Waiter enters total KES amount, and the system calculates quantity.
    Only accessible via HTMX click.
    """
    # Ensure it's an HTMX request
    if not request.htmx:
        return HttpResponse(status=405)

    # Get the menu item
    item = get_object_or_404(MenuItem, id=item_id)

    # Get the module (Kitchen/Bar) from query param - default to Bar
    module = request.GET.get('module', 'Bar')
    if module not in dict(Category.Module.choices):
        module = 'Bar'

    # Render the modal
    return render(request, 'pos/partials/_item_add_modal.html', {
        'item': item,
        'module': module,
    })


def _render_error_response(request, message):
    response = render(request, 'pos/partials/_stock_error.html', {
        'message': message,
        'timestamp': timezone.now(),
    })

    response['HX-Retarget'] = '#error-toast-container'
    response['HX-Reswap'] = 'beforeend'
    # Remove this line since template handles auto-dismiss:
    # response['HX-Trigger-After-Settle'] = 'dismissToast'

    return response


@login_required
def htmx_remove_order_item(request):
    """ Decrements an item's quantity in the cart. """
    if request.method == 'POST':
        item_id_str = request.POST.get('menu_item_id')
        module = request.POST.get('module')
        table_session = get_table_session(request)
        cart_name = 'kitchen_cart' if module == 'Kitchen' else 'bar_cart'
        session_cart = table_session[cart_name]

        if item_id_str in session_cart['items']:
            if session_cart['items'][item_id_str]['quantity'] > 1:
                session_cart['items'][item_id_str]['quantity'] -= 1
            else:
                del session_cart['items'][item_id_str]

            total = sum(
                Decimal(str(item['quantity'])) * Decimal(str(item['price'])) for item in session_cart['items'].values())
            session_cart['total'] = float(total)
            request.session.modified = True

        return render(request, 'pos/partials/_order_summary.html', {'cart': session_cart, 'module': module})
    return HttpResponse(status=405)


@login_required
def htmx_delete_order_item(request):
    """ Removes an item from the cart entirely, regardless of quantity. """
    if request.method == 'POST':
        item_id_str = request.POST.get('menu_item_id')
        module = request.POST.get('module')
        table_session = get_table_session(request)
        cart_name = 'kitchen_cart' if module == 'Kitchen' else 'bar_cart'
        session_cart = table_session[cart_name]

        if item_id_str in session_cart['items']:
            del session_cart['items'][item_id_str]
            total = sum(
                Decimal(str(item['quantity'])) * Decimal(str(item['price'])) for item in session_cart['items'].values())
            session_cart['total'] = float(total)
            request.session.modified = True

        return render(request, 'pos/partials/_order_summary.html', {'cart': session_cart, 'module': module})
    return HttpResponse(status=405)


@login_required
def htmx_clear_cart(request):
    """ Clears all items from a specific cart. """
    if request.method == 'POST':
        module = request.POST.get('module')
        table_session = get_table_session(request)
        cart_name = 'kitchen_cart' if module == 'Kitchen' else 'bar_cart'
        session_cart = table_session[cart_name]

        session_cart['items'] = {}
        session_cart['total'] = 0.0
        request.session.modified = True

        return render(request, 'pos/partials/_order_summary.html', {'cart': session_cart, 'module': module})
    return HttpResponse(status=405)


@login_required
def htmx_menu_panel(request):
    active_section = request.GET.get('section', 'Bar')

    # Get categories relevant for the dropdown
    relevant_categories = Category.objects.filter(module=active_section)

    # Get initial set of menu items for the active section
    menu_items = MenuItem.objects.filter(is_active=True, category__module=active_section, selling_price__gt=0 )

    context = {
        'menu_items': menu_items,
        'all_categories': relevant_categories,
        'active_section': active_section,
    }
    return render(request, 'pos/partials/_menu_panel.html', context)


# This view renders ONLY the menu item grid.
# It's called when a FILTER (search/category) is used.
@login_required
def htmx_menu_grid(request):
    section = request.GET.get('section', 'Bar')
    category_query = request.GET.get('category', '')
    search_query = request.GET.get('q', '').strip()

    menu_items = MenuItem.objects.filter(is_active=True, category__module=section, selling_price__gt=0 )
    if category_query:
        menu_items = menu_items.filter(category_id=category_query)
    if search_query:
        menu_items = menu_items.filter(name__icontains=search_query)

    context = {
        'menu_items': menu_items,
        'module': section,
    }
    return render(request, 'pos/partials/_menu_item_grid.html', context)


# ==============================================================================
# KDS & BDS (Kitchen/Bar Display) VIEWS
# ==============================================================================

@login_required
def kitchen_display_view(request):
    """ Renders the KDS with correctly filtered Kitchen items. """
    pending_orders = Order.objects.filter(
        items__menu_item__category__module='Kitchen',
        status=Order.Status.PENDING
    ).prefetch_related(
        Prefetch(
            'items',
            queryset=OrderItem.objects.filter(menu_item__category__module='Kitchen'),
            to_attr='module_items'  # This creates a new attribute with only kitchen items
        )
    ).distinct().order_by('created_at')

    for order in pending_orders:
        order.age = timezone.now() - order.created_at
        order.age_minutes = int(order.age.total_seconds() / 60)

    context = {'orders': pending_orders, 'display_title': 'Kitchen Display', 'module_type': 'Kitchen'}
    return render(request, 'pos/display_view.html', context)


@login_required
def bar_display_view(request):
    """ Renders the BDS with correctly filtered Bar items. """
    pending_orders = Order.objects.filter(
        items__menu_item__category__module='Bar',
        status=Order.Status.PENDING
    ).prefetch_related(
        Prefetch(
            'items',
            queryset=OrderItem.objects.filter(menu_item__category__module='Bar'),
            to_attr='module_items' # This creates a new attribute with only bar items
        )
    ).distinct().order_by('created_at')

    for order in pending_orders:
        order.age = timezone.now() - order.created_at
        order.age_minutes = int(order.age.total_seconds() / 60)

    context = {'orders': pending_orders, 'display_title': 'Bar Display', 'module_type': 'Bar'}
    return render(request, 'pos/display_view.html', context)


def htmx_mark_items_ready(request, order_id, module):
    """
    Marks an Order Docket as COMPLETED and triggers a print event for that specific docket.
    """
    if request.method == 'POST':
        order = get_object_or_404(Order, pk=order_id)

        # Update the parent Order's status to COMPLETED
        order.status = Order.Status.COMPLETED
        order.save()

        # Prepare the response that removes the ticket from the KDS
        response = HttpResponse(status=200)

        # HIGHLIGHT: Create a print event specifically for THIS order docket.
        print_url = reverse('pos:print_order_receipt', kwargs={'order_id': order.id})
        event_data = {'printUrl': print_url}

        # We'll use a more specific event name now: 'printDocket'
        response['HX-Trigger'] = json.dumps({"printDocket": event_data})

        return response
    return HttpResponse(status=405)

# ==============================================================================
# PRINTING & BILLING VIEWS
# ==============================================================================
@login_required
def print_order_receipt(request, order_id):
    """
    Prepares a printable production docket for a single order (Kitchen or Bar).
    Optimized for compact printing with minimal spacing.
    """
    order = get_object_or_404(
        Order.objects.prefetch_related('items__menu_item__category'),
        pk=order_id
    )

    first_item = order.items.first()
    receipt_title = "julifarm"
    if first_item:
        module_name = first_item.menu_item.category.get_module_display()
        receipt_title = f"Bilken Hotel {module_name}"

    context = {
        'order': order,
        'receipt_title': receipt_title,
        # Add these for better control
        'print_timestamp': timezone.now(),
        'total_items': order.items.count(),
        'is_thermal_print': request.GET.get('thermal', False),  # Optional thermal mode
    }

    # Use the compact template
    template_name = 'pos/print_receipt_compact.html'

    # Optional: Different template for thermal printers
    if context['is_thermal_print']:
        template_name = 'pos/print_receipt_thermal.html'

    response = render(request, template_name, context)

    # Optimize for printing
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'

    return response

@login_required
def generate_table_bill(request, table_id):
    """
    Generates the final, consolidated customer bill for all pending orders at a table.
    """
    table = get_object_or_404(Table, pk=table_id)
    orders_for_bill = Order.objects.filter(table=table, status=Order.Status.PENDING).prefetch_related(
        'items__menu_item')

    grand_total = sum(item.subtotal for order in orders_for_bill for item in order.items.all())

    context = {
        'table': table,
        'orders_for_bill': orders_for_bill,
        'grand_total': grand_total,
        'timestamp': timezone.now()
    }
    return render(request, 'pos/print_bill.html', context)


@login_required
def unified_station_view(request, section):
    section_name = section.capitalize()
    pending_orders = Order.objects.filter(
        status=Order.Status.PENDING,
        items__menu_item__category__module=section_name
    ).distinct().order_by('created_at').prefetch_related('items__menu_item__category')

    ready_orders = Order.objects.filter(
        status=Order.Status.READY,
        items__menu_item__category__module=section_name
    ).distinct().order_by('-updated_at')

    for order in pending_orders:
        order.age_minutes = int((timezone.now() - order.created_at).total_seconds() / 60)

    context = {
        'display_title': f"{section_name} Station",
        'module_type': section_name,
        'pending_orders': pending_orders,
        'ready_orders': ready_orders,
    }
    return render(request, 'pos/unified_station_view.html', context)


@login_required
def htmx_mark_as_ready_and_print(request, order_id):
    """
    Marks an order as READY and returns HTML to update both panels on the screen.
    This uses an advanced HTMX feature called an "Out of Band Swap".
    """
    if request.method == 'POST':
        order = get_object_or_404(Order, pk=order_id)
        order.status = Order.Status.READY
        order.save()

        # Get the module to refetch the correct list
        module = order.items.first().menu_item.category.module

        # Re-query the list of orders that are now ready for payment
        ready_orders = Order.objects.filter(
            status=Order.Status.READY,
            items__menu_item__category__module=module
        ).distinct().order_by('created_at')

        # Render the "Awaiting Payment" list into a string
        ready_list_html = render_to_string(
            'pos/partials/_awaiting_payment_list.html',
            {'ready_orders': ready_orders, 'module_type': module}
        )

        # Create a response that contains the new list, marked for an Out-of-Band swap
        # The main response is empty, which removes the original ticket.
        response = HttpResponse(
            f'<div id="awaiting-payment-list" hx-swap-oob="innerHTML">{ready_list_html}</div>',
            status=200
        )

        # Also trigger the printing event
        print_url = reverse('pos:print_order_receipt', kwargs={'order_id': order.id})
        event_data = {'printUrl': print_url}
        response['HX-Trigger'] = json.dumps({"printDocket": event_data})

        return response
    return HttpResponse(status=405)


@login_required
def htmx_payment_modal(request, order_id):
    order = get_object_or_404(Order.objects.select_related('customer'), pk=order_id)

    # Clear session discounts
    if 'loyalty_redemption' in request.session:
        del request.session['loyalty_redemption']
    if 'coupon_redemption' in request.session:
        del request.session['coupon_redemption']
    request.session.modified = True

    # ✅ Calculate final total due
    final_total_due = order.subtotal  # No VAT

    context = {
        'order': order,
        'final_total_due': final_total_due,
        'payment_methods': Sale.PaymentMethod.choices,
        'loyalty_settings': LoyaltySettings.objects.first(),
    }

    return render(request, 'pos/partials/_payment_screen.html', context)


@login_required
def process_order_payment(request, order_id):
    """
    Process order payment and handle:
      - Low-stock detection
      - Draft PO creation (or reuse)
      - Auto-adding items to POs
      - Waiter reward points (base points)
      - AUTOMATIC LEADERBOARD RECALCULATION (dynamic bonuses)
    """
    order = get_object_or_404(
        Order.objects.select_related('customer', 'table').prefetch_related('items__menu_item'),
        pk=order_id
    )

    if request.method != 'POST':
        return HttpResponse("Method Not Allowed", status=405)

    payment_method = request.POST.get('payment_method', '').strip()
    amount_paid_str = request.POST.get('amount_paid', '0').strip()
    mpesa_transaction_id = request.POST.get('mpesa_transaction_id', '').strip()

    valid_methods = [choice[0] for choice in Sale.PaymentMethod.choices]
    if payment_method not in valid_methods:
        return HttpResponse("Error: Invalid payment method selected.", status=400)

    try:
        amount_tendered = Decimal(amount_paid_str)
        if amount_tendered < 0:
            return HttpResponse("Error: Amount cannot be negative.", status=400)
    except:
        return HttpResponse("Error: Invalid amount format.", status=400)

    loyalty_redemption = request.session.get('loyalty_redemption', {})
    coupon_redemption = request.session.get('coupon_redemption', {})
    loyalty_discount = Decimal(str(loyalty_redemption.get('discount', '0.00')))
    coupon_discount = Decimal(str(coupon_redemption.get('discount', '0.00')))
    final_total_due = max(order.total_amount - loyalty_discount - coupon_discount, Decimal('0.00'))

    if payment_method == 'Mpesa' and not mpesa_transaction_id:
        return HttpResponse("Error: M-Pesa transaction ID is required.", status=400)

    if payment_method == 'Credit':
        customer = order.customer
        if customer.id == 1:
            return HttpResponse("Error: Credit not available for walk-in customers.", status=400)
        if customer.credit_balance + final_total_due > customer.credit_limit:
            return HttpResponse("Error: Credit limit exceeded.", status=400)

    def get_section_from_category(menu_item):
        mapping = {
            
            Category.Module.BAR: PurchaseOrder.Section.BAR,
            Category.Module.BUTCHERY: PurchaseOrder.Section.BUTCHERY,
        }
        return mapping[menu_item.category.module]

    def get_or_create_draft_purchase_order(supplier, section):
        admin_user = User.objects.filter(role='admin').first() or User.objects.filter(is_superuser=True).first()
        draft_po, created = PurchaseOrder.objects.get_or_create(
            supplier=supplier,
            status=PurchaseOrder.Status.DRAFT,
            requested_for_section=section,
            defaults={
                'created_by': admin_user,
                'notes': f"Auto-generated on {timezone.now():%Y-%m-%d %H:%M}",
            }
        )
        logger.info(f"{'Created' if created else 'Reused'} Draft PO: #{draft_po.id} for {supplier.name} [{section}]")
        return draft_po

    def add_item_to_purchase_order(po, menu_item, qty):
        try:
            line, created = PurchaseOrderItem.objects.get_or_create(
                purchase_order=po,
                menu_item=menu_item,
                defaults={
                    'quantity_ordered': qty,
                    'unit_price': menu_item.supplier_cost_price or Decimal('0.00'),
                }
            )
            if not created:
                line.quantity_ordered += qty
                line.save(update_fields=['quantity_ordered'])
                logger.info(f"Updated PO item: {menu_item.name} → qty {line.quantity_ordered}")
            else:
                logger.info(f"Added PO item: {menu_item.name} → qty {qty}")
        except Exception as e:
            logger.error(f"⚠️ Error saving PO item for {menu_item.name}: {e}")

    try:
        with transaction.atomic():
            if payment_method == 'Credit':
                customer = order.customer
                customer.credit_balance += final_total_due
                customer.save(update_fields=['credit_balance'])

            sale = Sale.objects.create(
                order=order,
                payment_method=payment_method,
                amount_paid=final_total_due,
                mpesa_transaction_id=mpesa_transaction_id,
                processed_at=timezone.now()
            )

            order.status = Order.Status.COMPLETED
            order.save(update_fields=['status'])

            low_stock_items = []

            for item in order.items.select_related('menu_item__category').prefetch_related(
                    'menu_item__recipe_items__ingredient'):
                menu_item = item.menu_item

                if menu_item.is_recipe:
                    for recipe_line in menu_item.recipe_items.all():
                        ingredient = recipe_line.ingredient
                        qty_used = item.quantity * recipe_line.quantity
                        db_ing = MenuItem.objects.select_for_update().get(pk=ingredient.pk)
                        db_ing.stock_quantity -= qty_used
                        db_ing.save(update_fields=['stock_quantity'])

                        if (db_ing.low_stock_threshold > 0 and
                                db_ing.stock_quantity <= db_ing.low_stock_threshold and
                                not StockAlert.objects.filter(menu_item=db_ing,
                                                              status=StockAlert.Status.ACTIVE).exists()):

                            logger.info(f"Low stock triggered: {db_ing.name} (Qty: {db_ing.stock_quantity})")
                            StockAlert.objects.create(menu_item=db_ing, stock_level_at_alert=db_ing.stock_quantity)
                            low_stock_items.append(db_ing.name)

                            if db_ing.preferred_supplier and db_ing.reorder_quantity > 0:
                                section = get_section_from_category(db_ing)
                                po = get_or_create_draft_purchase_order(db_ing.preferred_supplier, section)
                                add_item_to_purchase_order(po, db_ing, db_ing.reorder_quantity)

                else:
                    db_item = MenuItem.objects.select_for_update().get(pk=menu_item.pk)
                    db_item.stock_quantity -= item.quantity
                    db_item.save(update_fields=['stock_quantity'])

                    if (db_item.low_stock_threshold > 0 and
                            db_item.stock_quantity <= db_item.low_stock_threshold and
                            not StockAlert.objects.filter(menu_item=db_item, status=StockAlert.Status.ACTIVE).exists()):

                        logger.info(f"Low stock triggered: {db_item.name} (Qty: {db_item.stock_quantity})")
                        StockAlert.objects.create(menu_item=db_item, stock_level_at_alert=db_item.stock_quantity)
                        low_stock_items.append(db_item.name)

                        if db_item.preferred_supplier and db_item.reorder_quantity > 0:
                            section = get_section_from_category(db_item)
                            po = get_or_create_draft_purchase_order(db_item.preferred_supplier, section)
                            add_item_to_purchase_order(po, db_item, db_item.reorder_quantity)

            # Loyalty Points
            loyalty_settings = LoyaltySettings.objects.first()
            customer = order.customer
            if loyalty_settings and loyalty_settings.is_active and hasattr(customer, 'loyalty_points'):
                points_earned = math.floor(
                    order.total_amount / loyalty_settings.points_per_kes) if loyalty_settings.points_per_kes > 0 else 0
                points_redeemed = loyalty_redemption.get('points', 0)
                customer.loyalty_points += (points_earned - points_redeemed)
                customer.save(update_fields=['loyalty_points'])

            # Waiter Reward Points (BASE POINTS ONLY - not including bonus)
            waiter_reward_settings = WaiterRewardSettings.objects.first()
            waiter = order.waiter
            if waiter_reward_settings and waiter_reward_settings.is_active and hasattr(waiter, 'waiter_reward_points'):
                waiter_points_earned = math.floor(
                    order.total_amount / waiter_reward_settings.points_per_kes) if waiter_reward_settings.points_per_kes > 0 else 0
                if waiter_points_earned > 0:
                    # Add base points to total (bonus will be recalculated separately)
                    waiter.waiter_reward_points += waiter_points_earned
                    waiter.save(update_fields=['waiter_reward_points'])
                    logger.info(
                        f"Waiter '{waiter.get_full_name()}' earned {waiter_points_earned} base points from Order #{order.id}")

            if coupon_id := coupon_redemption.get('id'):
                Coupon.objects.filter(id=coupon_id).update(times_used=F('times_used') + 1)

            if order.table and not Order.objects.filter(table=order.table,
                                                        status__in=[Order.Status.PENDING, Order.Status.READY]).exists():
                order.table.status = Table.Status.AVAILABLE
                order.table.save(update_fields=['status'])

            for key in ['loyalty_redemption', 'coupon_redemption']:
                request.session.pop(key, None)
            request.session.modified = True

            change_due = max(amount_tendered - final_total_due, Decimal('0.00')) if payment_method in ['Cash',
                                                                                                       'Mpesa'] else Decimal(
                '0.00')
            success_message = f"Payment successful! Order #{order.id} completed."
            if change_due > 0:
                success_message += f" Change due: {change_due:.2f} KES"

            if low_stock_items:
                success_message += f"\\n\\nLow-stock alerts created for: {', '.join(low_stock_items[:3])}"
                if len(low_stock_items) > 3:
                    success_message += f" and {len(low_stock_items) - 3} more."
                success_message += "\\nDraft purchase orders have been generated."

        # CRITICAL: Trigger leaderboard recalculation AFTER transaction completes
        # This updates all waiter bonuses based on new rankings
        from pos.signals import recalculate_all_leaderboard_bonuses
        recalculate_all_leaderboard_bonuses()
        logger.info("🏆 Leaderboard recalculated after payment")

        return HttpResponse(f"""
            <script>
                const overlay = document.getElementById('payment-overlay');
                if (overlay) overlay.remove();
                alert('{success_message}');
                window.location.reload();
            </script>
        """, content_type='text/html')

    except Exception as e:
        logger.error(f"❌ Payment processing error: {str(e)}")
        traceback.print_exc()
        return HttpResponse(f"Unexpected server error: {str(e)}", status=500)

@login_required
def htmx_customer_search(request):
    """
    Handles HTMX requests for searching customers by name or phone number.
    Returns a partial HTML snippet with the search results.
    """
    query = request.GET.get('q', '').strip()

    if query:
        # Search for customers where the name or phone number contains the query.
        # Exclude the default "Walking In" customer from search results.
        customers = Customer.objects.filter(
            Q(name__icontains=query) | Q(phone_number__icontains=query)
        ).exclude(pk=1)[:10]  # Limit to the top 10 results
    else:
        customers = Customer.objects.none()  # Return no customers if the query is empty

    context = {'customers': customers}
    return render(request, 'pos/partials/_customer_search_results.html', context)


@login_required
def htmx_awaiting_payment_list(request, section):
    """
    Renders ONLY the list of orders awaiting payment for a specific section.
    Used for refreshing the list on the station dashboard.
    """
    section_name = section.capitalize()

    ready_orders = Order.objects.filter(
        status=Order.Status.READY,
        items__menu_item__category__module=section_name
    ).distinct().order_by('created_at')

    context = {
        'orders': ready_orders,
        'module_type': section_name
    }
    return render(request, 'pos/partials/_awaiting_payment_list.html', context)


@login_required
def htmx_mark_one_item_ready(request, item_id):
    if request.method != 'POST': return HttpResponse(status=405)

    with transaction.atomic():
        order_item = get_object_or_404(OrderItem.objects.select_related('order', 'menu_item__category'), pk=item_id)
        if order_item.status == OrderItem.Status.PENDING:
            order_item.status = OrderItem.Status.READY
            order_item.save()

        parent_order = order_item.order
        is_order_fully_complete = not parent_order.items.filter(status=OrderItem.Status.PENDING).exists()

        if is_order_fully_complete:
            parent_order.status = Order.Status.READY
            parent_order.save(update_fields=['status'])
            # Send the signal. The response itself is empty.
            response = HttpResponse(status=204)
            response['HX-Trigger'] = 'orderCompleted'
            return response
        else:
            # The order isn't fully ready, so just refresh the single ticket
            parent_order.age_minutes = int((timezone.now() - parent_order.created_at).total_seconds() / 60)
            context = {'order': parent_order, 'module_type': order_item.menu_item.category.module}
            return render(request, 'pos/partials/_station_ticket.html', context)


@login_required
def sales_report_view(request):
    """
    Generates and displays the sales report. The filtering logic is now
    simplified to only use the date range, and the HTMX response has been
    updated to fix the print button issue. Now includes payment method breakdown.
    """
    today = timezone.now().date()

    # Default date range: last 7 days
    start_date_str = request.GET.get('start_date', (today - timedelta(days=7)).strftime('%Y-%m-%d'))
    end_date_str = request.GET.get('end_date', today.strftime('%Y-%m-%d'))

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        start_date = today - timedelta(days=7)
        end_date = today

    # All sales in range
    sales_in_range = Sale.objects.filter(
        processed_at__date__range=[start_date, end_date]
    )

    # All order IDs for those sales
    orders_in_range = sales_in_range.values_list('order_id', flat=True)

    # Base queryset for all completed order items linked to those sales
    base_sales_items = OrderItem.objects.filter(
        order__status=Order.Status.COMPLETED,
        order_id__in=orders_in_range
    ).select_related('menu_item__category')

    # 🔹 Payment method breakdown
    payment_methods = sales_in_range.values('payment_method').annotate(
        total_sales=Sum('amount_paid'),
        sale_count=Count('id')
    ).order_by('-total_sales')

    # Add human-readable display name for payment method
    PAYMENT_METHOD_LOOKUP = dict(Sale.PaymentMethod.choices)
    for method in payment_methods:
        method['display_name'] = PAYMENT_METHOD_LOOKUP.get(
            method['payment_method'],
            method['payment_method']
        )

    # 🔹 Summary by Section
    section_summary = base_sales_items.values('menu_item__category__module').annotate(
        total_items=Sum('quantity'),
        total_sales=Sum(F('quantity') * F('price_at_sale'))
    ).order_by('-total_sales')

    # 🔹 Summary by Category
    category_summary = base_sales_items.values('menu_item__category__name').annotate(
        total_items=Sum('quantity'),
        total_sales=Sum(F('quantity') * F('price_at_sale'))
    ).order_by('-total_sales')

    # 🔹 Detailed list of all items
    item_details = base_sales_items.values('menu_item__name', 'price_at_sale').annotate(
        items_sold=Sum('quantity'),
        total_price=Sum(F('quantity') * F('price_at_sale'))
    ).order_by('-total_price')

    # 🔹 FIXED: Grand total should match payment methods total
    # Option 1: Use the same source as payment methods (Sales.amount_paid)
    grand_total = sales_in_range.aggregate(
        total=Sum('amount_paid')
    )['total'] or Decimal('0.00')

    # Option 2: Calculate from payment methods (ensures consistency)
    # grand_total = sum(method['total_sales'] for method in payment_methods)

    # 🔹 Alternative: Calculate both and show discrepancy if needed
    grand_total_from_sales = sales_in_range.aggregate(
        total=Sum('amount_paid')
    )['total'] or Decimal('0.00')

    grand_total_from_items = base_sales_items.aggregate(
        total=Sum(F('quantity') * F('price_at_sale'))
    )['total'] or Decimal('0.00')

    # Use sales total for payment method percentages
    grand_total = grand_total_from_sales

    # Add debug info to context
    has_discrepancy = abs(grand_total_from_sales - grand_total_from_items) > Decimal('0.01')

    # Calculate additional summary stats
    total_items_quantity = base_sales_items.aggregate(
        total=Sum('quantity')
    )['total'] or 0

    unique_items_sold = base_sales_items.values('menu_item').distinct().count()
    total_transactions = sales_in_range.count()

    context = {
        'section_summary': section_summary,
        'category_summary': category_summary,
        'item_details': item_details,
        'payment_methods': payment_methods,
        'grand_total': grand_total,

        # 🔹 FIX: Pass date objects, not strings, so Django template filters work
        'start_date': start_date,  # Keep as date object
        'end_date': end_date,      # Keep as date object
        'ran_at': timezone.now(),

        # Additional summary stats
        'total_items_quantity': total_items_quantity,
        'unique_items_sold': unique_items_sold,
        'total_transactions': total_transactions,

        # Debug info (remove after fixing)
        'grand_total_from_sales': grand_total_from_sales,
        'grand_total_from_items': grand_total_from_items,
        'has_discrepancy': has_discrepancy,
        'payment_methods_sum': sum(method['total_sales'] for method in payment_methods),
    }

    if request.htmx:
        return render(request, 'pos/partials/sales_report_content.html', context)

    return render(request, 'pos/sales_report.html', context)


@login_required
def print_sales_report_view(request):
    """
    Debug version with extensive logging to identify calculation issues.
    """
    today = timezone.now().date()

    # Get date parameters with better validation
    start_date_str = request.GET.get('start_date', (today - timedelta(days=7)).strftime('%Y-%m-%d'))
    end_date_str = request.GET.get('end_date', today.strftime('%Y-%m-%d'))

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

        if start_date > end_date:
            start_date, end_date = end_date, start_date

    except (ValueError, TypeError):
        start_date = today - timedelta(days=7)
        end_date = today

    print(f"DEBUG: Date range: {start_date} to {end_date}")

    # Step 1: Get all sales in range
    sales_in_range = Sale.objects.filter(
        processed_at__date__range=[start_date, end_date]
    )
    print(f"DEBUG: Found {sales_in_range.count()} sales in range")

    # Debug: Print first few sales
    for sale in sales_in_range[:3]:
        print(f"DEBUG: Sale {sale.id} - Order {sale.order_id} - Amount {sale.amount_paid}")

    # Step 2: Get all order IDs for those sales
    orders_in_range = list(sales_in_range.values_list('order_id', flat=True))
    print(f"DEBUG: Found {len(orders_in_range)} unique order IDs: {orders_in_range[:5]}...")

    # Step 3: Get all completed order items for those orders
    base_sales_items = OrderItem.objects.filter(
        order__status=Order.Status.COMPLETED,
        order_id__in=orders_in_range
    ).select_related('menu_item__category')

    print(f"DEBUG: Found {base_sales_items.count()} order items")

    # Debug: Print first few order items
    for item in base_sales_items[:3]:
        print(f"DEBUG: Item {item.id} - {item.menu_item.name} - Qty: {item.quantity} - Price: {item.price_at_sale}")

    # Step 4: Check if we have any items at all
    if not base_sales_items.exists():
        print("DEBUG: No order items found! Checking raw data...")

        # Check if orders exist
        all_orders = list(Order.objects.filter(id__in=orders_in_range).values('id', 'status'))
        print(f"DEBUG: Orders found: {all_orders}")

        # Check if items exist for any status
        all_items = OrderItem.objects.filter(order_id__in=orders_in_range)
        print(f"DEBUG: All order items (any status): {all_items.count()}")

        for item in all_items[:3]:
            print(f"DEBUG: Any Item {item.id} - Order {item.order_id} - Status: {item.order.status}")

    # 🔹 Payment method breakdown
    payment_methods = sales_in_range.values('payment_method').annotate(
        total_sales=Sum('amount_paid'),
        sale_count=Count('id')
    ).order_by('-total_sales')

    print(f"DEBUG: Payment methods: {list(payment_methods)}")

    PAYMENT_METHOD_LOOKUP = dict(Sale.PaymentMethod.choices)
    for method in payment_methods:
        method['display_name'] = PAYMENT_METHOD_LOOKUP.get(
            method['payment_method'],
            method['payment_method']
        )

    # 🔹 Summary by Section
    section_summary = base_sales_items.values(
        'menu_item__category__module'
    ).annotate(
        total_items=Sum('quantity'),
        total_sales=Sum(F('quantity') * F('price_at_sale'))
    ).exclude(
        menu_item__category__module__isnull=True
    ).order_by('-total_sales')

    print(f"DEBUG: Section summary: {list(section_summary)}")

    # 🔹 Summary by Category
    category_summary = base_sales_items.values(
        'menu_item__category__name'
    ).annotate(
        total_items=Sum('quantity'),
        total_sales=Sum(F('quantity') * F('price_at_sale'))
    ).exclude(
        menu_item__category__name__isnull=True
    ).order_by('-total_sales')

    print(f"DEBUG: Category summary: {list(category_summary)}")

    # 🔹 Detailed list of all items
    item_details = base_sales_items.values(
        'menu_item__name',
        'price_at_sale'
    ).annotate(
        items_sold=Sum('quantity'),
        total_price=Sum(F('quantity') * F('price_at_sale'))
    ).exclude(
        menu_item__name__isnull=True
    ).order_by('-total_price')

    print(f"DEBUG: Item details count: {item_details.count()}")
    print(f"DEBUG: First few items: {list(item_details[:3])}")

    # 🔹 Grand total calculations
    grand_total_from_sales = sales_in_range.aggregate(
        total=Sum('amount_paid')
    )['total'] or Decimal('0.00')

    grand_total_from_items = base_sales_items.aggregate(
        total=Sum(F('quantity') * F('price_at_sale'))
    )['total'] or Decimal('0.00')

    grand_total = grand_total_from_sales
    payment_methods_sum = sum(method['total_sales'] or Decimal('0.00') for method in payment_methods)
    has_discrepancy = abs(grand_total_from_sales - grand_total_from_items) > Decimal('0.01')

    # Additional calculations
    total_transactions = sales_in_range.count()
    unique_items_sold = item_details.count()
    total_items_quantity = base_sales_items.aggregate(
        total_qty=Sum('quantity')
    )['total_qty'] or 0

    print(f"DEBUG: Grand totals - Sales: {grand_total_from_sales}, Items: {grand_total_from_items}")
    print(f"DEBUG: Total qty: {total_items_quantity}")

    context = {
        'section_summary': section_summary,
        'category_summary': category_summary,
        'item_details': item_details,
        'payment_methods': payment_methods,
        'grand_total': grand_total,
        'start_date': start_date,
        'end_date': end_date,
        'ran_at': timezone.now(),

        # Stats
        'total_transactions': total_transactions,
        'unique_items_sold': unique_items_sold,
        'total_items_quantity': total_items_quantity,

        # Debug info
        'grand_total_from_sales': grand_total_from_sales,
        'grand_total_from_items': grand_total_from_items,
        'has_discrepancy': has_discrepancy,
        'payment_methods_sum': payment_methods_sum,

        # Additional debug
        'debug_sales_count': sales_in_range.count(),
        'debug_items_count': base_sales_items.count(),
        'debug_orders_count': len(orders_in_range),

        # Date info
        'date_range_days': (end_date - start_date).days + 1,
        'is_single_day': start_date == end_date,
    }

    return render(request, 'pos/print_sales_report.html', context)



@login_required  # Or a specific admin/manager decorator
def customer_list(request):
    """
    Displays a paginated customer list with live, predictive search powered by HTMX.
    - On initial load (no search query), it lists ALL customers.
    - On HTMX request (with a search query), it lists FILTERED customers.
    """

    # 1. Get the search query from the URL. Defaults to an empty string if not present.
    query = request.GET.get('q', '').strip()

    # 2. Start with a base queryset of ALL customers, ordered by name.
    customer_queryset = Customer.objects.all().order_by('name')

    # 3. If a search query exists, filter the queryset.
    if query:
        # Use Q objects to search by name (predictive) OR phone number (contains).
        customer_queryset = customer_queryset.filter(
            Q(name__istartswith=query) | Q(phone_number__icontains=query)
        )

    # 4. Paginate the result (either the full list or the filtered list).
    paginator = Paginator(customer_queryset, 20)  # Show 20 customers per page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search_query': query,
    }

    # 5. Check if the request is from HTMX (i.e., a search or pagination click).
    if request.htmx:
        # If it is, return only the partial template with the table rows.
        return render(request, 'pos/partials/_customer_table.html', context)

    # If it's a normal, full page load, return the main page shell.
    return render(request, 'pos/customer_list.html', context)


@login_required
def customer_add(request):
    """
    Handles the creation of a new customer.
    """
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f"Customer '{form.cleaned_data['name']}' was added successfully.")
            return redirect('pos:customer_list')
    else:
        form = CustomerForm()

    context = {
        'form': form,
        'form_title': 'Add New Customer'
    }
    return render(request, 'pos/customer_form.html', context)


@login_required
def customer_edit(request, pk):
    """
    Handles editing an existing customer.
    """
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            messages.success(request, f"Customer '{customer.name}' was updated successfully.")
            return redirect('pos:customer_list')
    else:
        form = CustomerForm(instance=customer)

    context = {
        'form': form,
        'form_title': f'Edit Customer: {customer.name}'
    }
    return render(request, 'pos/customer_form.html', context)


@login_required
def customer_delete(request, pk):
    """
    Handles deleting a customer after confirmation.
    """
    customer = get_object_or_404(Customer, pk=pk)

    # Optional: Prevent deletion if there is an outstanding credit balance
    if customer.credit_balance > 0:
        messages.error(request,
                       f"Cannot delete '{customer.name}' because they have an outstanding credit balance of {customer.credit_balance} KES.")
        return redirect('pos:customer_list')

    if request.method == 'POST':
        customer_name = customer.name
        try:
            customer.delete()
            messages.success(request, f"Customer '{customer_name}' has been deleted.")
        except Exception as e:
            messages.error(request,
                           f"Cannot delete '{customer_name}' as they are linked to existing orders. Error: {e}")
        return redirect('pos:customer_list')

    context = {'customer': customer}
    return render(request, 'pos/customer_confirm_delete.html', context)


@login_required  # Or a specific admin/manager decorator
def table_list(request):
    """
    Displays a list of all restaurant tables.
    """
    tables = Table.objects.all().order_by('table_number')
    context = {'tables': tables}
    return render(request, 'pos/table_list.html', context)


@login_required
def table_add(request):
    """
    Handles the creation of a new table.
    """
    if request.method == 'POST':
        form = TableForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f"Table '{form.cleaned_data['table_number']}' was added successfully.")
            return redirect('pos:table_list')
    else:
        form = TableForm()

    context = {
        'form': form,
        'form_title': 'Add New Table'
    }
    return render(request, 'pos/table_form.html', context)


@login_required
def table_edit(request, pk):
    """
    Handles editing an existing table.
    """
    table = get_object_or_404(Table, pk=pk)
    if request.method == 'POST':
        form = TableForm(request.POST, instance=table)
        if form.is_valid():
            form.save()
            messages.success(request, f"Table '{table.table_number}' was updated successfully.")
            return redirect('pos:table_list')
    else:
        form = TableForm(instance=table)

    context = {
        'form': form,
        'form_title': f'Edit Table: {table.table_number}'
    }
    return render(request, 'pos/table_form.html', context)


@login_required
def table_delete(request, pk):
    """
    Handles deleting a table after confirmation, with a check to prevent
    deleting an occupied table.
    """
    table = get_object_or_404(Table, pk=pk)

    # Critical business rule: do not allow deletion of an occupied table.
    if table.status == Table.Status.OCCUPIED:
        messages.error(request, f"Cannot delete Table '{table.table_number}' because it is currently occupied.")
        return redirect('pos:table_list')

    if request.method == 'POST':
        table_number = table.table_number
        try:
            table.delete()
            messages.success(request, f"Table '{table_number}' has been deleted.")
        except Exception as e:
            messages.error(request, f"An error occurred while trying to delete the table: {e}")
        return redirect('pos:table_list')

    context = {'table': table}
    return render(request, 'pos/table_confirm_delete.html', context)


@login_required  # Or a specific admin/manager decorator
def customer_payment_list(request):
    """
    Lists all historical customer credit payments for auditing.
    This is the answer to "should I have them listed?". Yes.
    """
    payments = CustomerPayment.objects.all().order_by('-payment_date').select_related('customer', 'processed_by')

    context = {'payments': payments}
    return render(request, 'pos/customer_payment_list.html', context)


@login_required
def add_customer_payment(request):
    """
    Handles the form for recording a new customer debt payment.
    - On GET, it displays the form, providing a filtered list of customers who have debt.
    - On POST, it validates the form, processes the payment, updates the customer's
      credit balance, and saves the transaction.
    """
    if request.method == 'POST':
        form = CustomerPaymentForm(request.POST)
        if form.is_valid():
            try:
                # Use a transaction to ensure both database actions succeed or fail together
                with transaction.atomic():
                    # Get the validated data from the form
                    customer = form.cleaned_data['customer']
                    amount_paid = form.cleaned_data['amount_paid']

                    # 1. Decrease the customer's outstanding credit balance
                    customer.credit_balance -= amount_paid
                    customer.save()

                    # 2. Prepare the payment record but don't save it yet
                    payment = form.save(commit=False)

                    # 3. Assign the currently logged-in user for accountability
                    payment.processed_by = request.user

                    # 4. Now, save the complete payment record to the database
                    payment.save()

                    messages.success(request,
                                     f"Payment of {amount_paid} KES for {customer.name} was recorded successfully. Their new balance is {customer.credit_balance} KES.")
                    return redirect('pos:customer_payment_list')

            except Exception as e:
                messages.error(request, f"An error occurred while processing the payment: {e}")
    else:
        form = CustomerPaymentForm()

    # For the GET request, fetch only customers who actually owe money
    customers_with_debt = Customer.objects.filter(credit_balance__gt=0).order_by('name')

    context = {
        'form': form,
        'form_title': 'Record Customer Debt Payment',
        'customers_with_debt': customers_with_debt,  # Pass the filtered list to the template
    }
    return render(request, 'pos/add_customer_payment.html', context)


@login_required
def credit_sales_report_view(request):
    """
    Handles the main interactive Credit Sales Report page, including the
    HTMX filtering logic.
    """
    today = timezone.now().date()
    # Default to showing the last 30 days
    start_date_str = request.GET.get('start_date', (today - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date_str = request.GET.get('end_date', today.strftime('%Y-%m-%d'))
    customer_filter = request.GET.get('customer', '')

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        start_date = today - timedelta(days=30)
        end_date = today

    # --- Data Fetching and Aggregation ---

    # Base queryset for all credit sales in the period
    credit_sales = Sale.objects.filter(
        payment_method=Sale.PaymentMethod.CREDIT,
        processed_at__date__range=[start_date, end_date]
    ).select_related('order__customer', 'order__waiter').order_by('-processed_at')

    # Base queryset for all credit payments received in the period
    payments_received = CustomerPayment.objects.filter(
        payment_date__date__range=[start_date, end_date]
    )

    # Apply optional customer filter to both querysets if provided
    if customer_filter:
        credit_sales = credit_sales.filter(order__customer_id=customer_filter)
        payments_received = payments_received.filter(customer_id=customer_filter)

    # HIGHLIGHT: Calculate the two key summary metrics for the report
    total_credit_sales_in_period = credit_sales.aggregate(
        total=Sum(F('order__subtotal') + F('order__vat_amount') + F('order__service_charge_amount'))
    )['total'] or Decimal('0.00')

    total_payments_in_period = payments_received.aggregate(
        total=Sum('amount_paid')
    )['total'] or Decimal('0.00')

    context = {
        'credit_sales': credit_sales,
        'total_credit_sales_in_period': total_credit_sales_in_period,
        'total_payments_in_period': total_payments_in_period,
        'all_customers': Customer.objects.filter(credit_balance__gt=0).order_by('name'),
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'customer_filter': customer_filter,
    }

    # If this is an HTMX request, render the wrapper partial to update the
    # print button link along with the report content.
    if request.htmx:
        return render(request, 'pos/partials/_printable_report_wrapper.html', context)

    # On initial page load, render the full page.
    return render(request, 'pos/credit_sales_report.html', context)


@login_required
def print_credit_sales_report_view(request):
    """
    Gathers the same data as the main credit report but renders the clean,
    printer-friendly version.
    """
    today = timezone.now().date()
    start_date_str = request.GET.get('start_date', today.strftime('%Y-%m-%d'))
    end_date_str = request.GET.get('end_date', today.strftime('%Y-%m-%d'))
    customer_filter = request.GET.get('customer', '')

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        start_date = today
        end_date = today

    # The data fetching and aggregation logic is identical to the main view
    # to ensure the printed report matches what is shown on screen.
    credit_sales = Sale.objects.filter(
        payment_method=Sale.PaymentMethod.CREDIT,
        processed_at__date__range=[start_date, end_date]
    ).select_related('order__customer', 'order__waiter').order_by('processed_at')

    payments_received = CustomerPayment.objects.filter(
        payment_date__date__range=[start_date, end_date]
    )

    selected_customer = None
    if customer_filter:
        credit_sales = credit_sales.filter(order__customer_id=customer_filter)
        payments_received = payments_received.filter(customer_id=customer_filter)
        selected_customer = get_object_or_404(Customer, pk=customer_filter)

    total_credit_sales_in_period = credit_sales.aggregate(
        total=Sum(F('order__subtotal') + F('order__vat_amount') + F('order__service_charge_amount')))[
                                       'total'] or Decimal('0.00')
    total_payments_in_period = payments_received.aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00')

    context = {
        'credit_sales': credit_sales,
        'total_credit_sales_in_period': total_credit_sales_in_period,
        'total_payments_in_period': total_payments_in_period,
        'start_date': start_date,
        'end_date': end_date,
        'selected_customer': selected_customer,
        'ran_at': timezone.now(),
    }

    return render(request, 'pos/print_credit_sales_report.html', context)


@login_required
def htmx_get_customer_balance(request):
    """
    An HTMX endpoint that returns the current credit balance for a selected customer.
    """
    customer_id = request.GET.get('customer')  # It looks for the 'customer' parameter
    if not customer_id:
        return HttpResponse("")

    customer = get_object_or_404(Customer, id=customer_id)

    return HttpResponse(f"""
        <div class="notification is-info is-light mt-2">
            <p>Current Outstanding Balance: <strong class="is-size-5">{customer.credit_balance} KES</strong></p>
        </div>
    """)


@login_required
def htmx_apply_coupon(request, order_id):
    """
    Validates a coupon code submitted via HTMX and returns an updated
    bill summary partial.
    """
    if request.method != 'POST':
        return HttpResponse(status=405)

    order = get_object_or_404(Order, pk=order_id)
    code = request.POST.get('coupon_code', '').strip().upper()
    coupon_discount = Decimal('0.00')

    # Clear any previous coupon to ensure only one is applied
    if 'coupon_redemption' in request.session:
        del request.session['coupon_redemption']

    try:
        if not code:
            raise ValueError("Please enter a coupon code.")

        coupon = Coupon.objects.get(code__iexact=code)

        # --- Validation Checks ---
        if not coupon.is_active: raise ValueError("This coupon is not active.")
        if coupon.times_used >= coupon.max_uses: raise ValueError("This coupon has reached its usage limit.")
        now = timezone.now()
        if not (coupon.valid_from <= now <= coupon.valid_until): raise ValueError(
            "This coupon is expired or not yet valid.")

        # --- If all checks pass, calculate discount ---
        base_amount = order.total_amount
        if coupon.discount_type == Coupon.DiscountType.PERCENTAGE:
            discount_amount = (base_amount * (coupon.value / 100)).quantize(Decimal('0.01'))
        else:  # Fixed amount
            discount_amount = coupon.value

        # Ensure discount doesn't exceed the total
        coupon_discount = min(base_amount, discount_amount)

        # Store valid coupon details in the session for final processing
        request.session['coupon_redemption'] = {
            'id': coupon.id,
            'code': coupon.code,
            'discount': float(coupon_discount)
        }

    except (Coupon.DoesNotExist, ValueError) as e:
        # On error, we can return an OOB swap to show feedback without breaking the page
        error_html = f"<div id='coupon-feedback-wrapper' hx-swap-oob='true'><p class='help is-danger'>{e}</p></div>"
        return HttpResponse(error_html)

    # --- Prepare context for the response partial ---
    request.session.modified = True
    loyalty_discount = Decimal(request.session.get('loyalty_redemption', {}).get('discount', '0.00'))
    final_total_due = order.total_amount - loyalty_discount - coupon_discount

    context = {
        'order': order,
        'loyalty_discount': loyalty_discount,
        'points_redeemed': request.session.get('loyalty_redemption', {}).get('points', 0),
        'coupon_discount': coupon_discount,
        'coupon_code': code,
        'final_total_due': final_total_due,
    }

    # Also include positive feedback on success via OOB Swap
    success_html = f"<div id='coupon-feedback-wrapper' hx-swap-oob='true'><p class='help is-success'>Coupon '{code}' applied successfully.</p></div>"
    main_html = render_to_string('pos/partials/_bill_discounts_and_total.html', context)

    return HttpResponse(main_html + success_html)


@login_required
def htmx_apply_loyalty_discount(request, order_id):
    """
    Applies customer loyalty points as a discount and returns an updated
    bill summary partial.
    """
    if request.method != 'POST':
        return HttpResponse(status=405)

    order = get_object_or_404(Order.objects.select_related('customer'), pk=order_id)
    customer = order.customer
    points_to_redeem_str = request.POST.get('points_to_redeem', '0')
    points_to_redeem = int(points_to_redeem_str) if points_to_redeem_str.isdigit() else 0
    loyalty_discount = Decimal('0.00')

    settings = LoyaltySettings.objects.first()
    if not settings or not settings.is_active:
        return HttpResponse("Error: Loyalty system is not active.", status=400)

    # --- Validation Checks ---
    if points_to_redeem <= 0:
        # If user clears the input, just remove the discount
        if 'loyalty_redemption' in request.session:
            del request.session['loyalty_redemption']
    elif points_to_redeem > customer.loyalty_points:
        return HttpResponse("Redemption amount exceeds customer's points balance.", status=400)
    elif points_to_redeem < settings.minimum_redeemable_points:
        return HttpResponse(f"A minimum of {settings.minimum_redeemable_points} points is required to redeem.",
                            status=400)
    else:
        # --- If validation passes, calculate discount ---
        discount_amount = (Decimal(points_to_redeem) * settings.kes_per_point).quantize(Decimal('0.01'))

        # Ensure discount doesn't exceed the total. If so, adjust points used.
        base_amount = order.total_amount
        if discount_amount > base_amount:
            loyalty_discount = base_amount
            points_to_redeem = int(loyalty_discount / settings.kes_per_point)
        else:
            loyalty_discount = discount_amount

        # Store redemption details in the session
        request.session['loyalty_redemption'] = {'points': points_to_redeem, 'discount': float(loyalty_discount)}

    # --- Prepare context for the response partial ---
    request.session.modified = True
    coupon_discount = Decimal(request.session.get('coupon_redemption', {}).get('discount', '0.00'))
    final_total_due = order.total_amount - loyalty_discount - coupon_discount

    context = {
        'order': order,
        'loyalty_discount': loyalty_discount,
        'points_redeemed': request.session.get('loyalty_redemption', {}).get('points', 0),
        'coupon_discount': coupon_discount,
        'coupon_code': request.session.get('coupon_redemption', {}).get('code'),
        'final_total_due': final_total_due,
    }

    return render(request, 'pos/partials/_bill_discounts_and_total.html', context)


@login_required
def expense_add(request):
    """
    Handles the form for adding a new business expense.
    """
    if request.method == 'POST':
        form = ExpenseForm(request.POST, request.FILES)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.recorded_by = request.user
            expense.save()
            messages.success(request, f"Expense of {expense.amount} KES for '{expense.category.name}' recorded.")
            return redirect('pos:expense_list')
    else:
        form = ExpenseForm()

    context = {'form': form}
    return render(request, 'pos/expense_form.html', context)


@login_required
def expense_edit(request, pk):
    """
    Handles editing an existing business expense.
    """
    # Fetch the specific expense record we want to edit, or return a 404 error if not found
    expense = get_object_or_404(Expense, pk=pk)

    # If the form is being submitted with new data
    if request.method == 'POST':
        # Create a form instance and populate it with data from the request,
        # including any files, and link it to the existing expense instance.
        form = ExpenseForm(request.POST, request.FILES, instance=expense)
        if form.is_valid():
            form.save()  # Save the changes to the existing expense record
            messages.success(request, f"Expense '{expense.description[:30]}...' was updated successfully.")
            return redirect('pos:expense_list')
    # If it's a GET request (i.e., the user is just visiting the edit page)
    else:
        # Create a form instance and pre-populate it with data from the existing expense
        form = ExpenseForm(instance=expense)

    context = {
        'form': form,
        'form_title': f"Edit Expense Record"
    }
    return render(request, 'pos/expense_form.html', context)


@login_required
def expense_list(request):
    """
    Handles the main interactive Expense Report. It displays a detailed list of
    expenses by default, with dynamic filtering by date, category, and description.
    """
    # --- 1. Get Filters from Request, with sensible defaults ---
    today = timezone.now().date()
    # Default to showing the last 30 days
    start_date_str = request.GET.get('start_date', (today - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date_str = request.GET.get('end_date', today.strftime('%Y-%m-%d'))
    category_filter = request.GET.get('category', '')
    search_query = request.GET.get('q', '').strip()

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        start_date = today - timedelta(days=30)
        end_date = today

    # --- 2. Filter Expenses based on parameters ---
    expenses = Expense.objects.select_related('category', 'recorded_by').filter(
        expense_date__range=[start_date, end_date]
    )

    if category_filter:
        expenses = expenses.filter(category_id=category_filter)
    if search_query:
        expenses = expenses.filter(description__icontains=search_query)

    # --- 3. Calculate Total for the Filtered Period ---
    total_expenses = expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    context = {
        'expenses': expenses.order_by('-expense_date'),
        'total_expenses': total_expenses,
        'all_categories': ExpenseCategory.objects.all(),
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'category_filter': category_filter,
        'search_query': search_query,
    }

    # --- 4. Handle HTMX vs. Full Page Load ---
    if request.htmx:
        # For HTMX requests, render only the wrapper partial to keep the print button synced
        return render(request, 'pos/partials/_printable_expense_wrapper.html', context)

    # On initial page load, render the full page shell
    return render(request, 'pos/expense_list.html', context)


@login_required
def print_expense_report_view(request):
    """
    Gathers the same filtered data as the main expense report but renders the
    clean, printer-friendly version.
    """
    # This view reuses the exact same filtering and aggregation logic
    # to ensure the printed report always matches what the user sees on screen.
    today = timezone.now().date()
    start_date_str = request.GET.get('start_date', (today - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date_str = request.GET.get('end_date', today.strftime('%Y-%m-%d'))
    category_filter = request.GET.get('category', '')
    search_query = request.GET.get('q', '').strip()

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        start_date = today - timedelta(days=30)
        end_date = today

    expenses = Expense.objects.select_related('category', 'recorded_by').filter(
        expense_date__range=[start_date, end_date]
    )
    if category_filter:
        expenses = expenses.filter(category_id=category_filter)
    if search_query:
        expenses = expenses.filter(description__icontains=search_query)

    total_expenses = expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    context = {
        'expenses': expenses.order_by('expense_date'),  # Order chronologically for print
        'total_expenses': total_expenses,
        'start_date': start_date,
        'end_date': end_date,
        'ran_at': timezone.now(),
    }

    return render(request, 'pos/print_expense_report.html', context)


@login_required  # Should be for managers/admins
def expense_category_list(request):
    """Lists and searches all expense categories."""
    query = request.GET.get('q', '').strip()
    categories = ExpenseCategory.objects.all()
    if query:
        categories = categories.filter(name__icontains=query)
    context = {'categories': categories, 'search_query': query}
    return render(request, 'pos/expense_category_list.html', context)


@login_required
def expense_category_add(request):
    """Handles adding a new expense category."""
    if request.method == 'POST':
        form = ExpenseCategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f"Category '{form.cleaned_data['name']}' created successfully.")
            return redirect('pos:expense_category_list')
    else:
        form = ExpenseCategoryForm()
    context = {'form': form, 'form_title': 'Add New Expense Category'}
    return render(request, 'pos/expense_category_form.html', context)


@login_required
def expense_category_edit(request, pk):
    """Handles editing an existing expense category."""
    category = get_object_or_404(ExpenseCategory, pk=pk)
    if request.method == 'POST':
        form = ExpenseCategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, f"Category '{category.name}' updated successfully.")
            return redirect('pos:expense_category_list')
    else:
        form = ExpenseCategoryForm(instance=category)
    context = {'form': form, 'form_title': f'Edit Category: {category.name}'}
    return render(request, 'pos/expense_category_form.html', context)


@login_required
def expense_category_delete(request, pk):
    """Handles deleting an expense category after confirmation."""
    category = get_object_or_404(ExpenseCategory, pk=pk)
    if category.expenses.exists():
        messages.error(request,
                       f"Cannot delete '{category.name}' because it is being used by existing expense records.")
        return redirect('pos:expense_category_list')

    if request.method == 'POST':
        category_name = category.name
        category.delete()
        messages.success(request, f"Category '{category_name}' has been deleted.")
        return redirect('pos:expense_category_list')

    context = {'category': category}
    return render(request, 'pos/expense_category_confirm_delete.html', context)


@login_required
def expense_delete(request, pk):
    """Handles deleting an expense record after confirmation."""
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        expense.delete()
        messages.success(request, "The expense record has been deleted.")
        return redirect('pos:expense_list')

    context = {'expense': expense}
    return render(request, 'pos/expense_confirm_delete.html', context)


@login_required
def print_customer_receipt(request, sale_id):
    """
    Prepares a printable receipt for a finalized sale.
    FIX: Now includes the section (Kitchen/Bar) the sale belongs to.
    """
    try:
        sale = Sale.objects.select_related(
            'order', 'order__customer', 'order__waiter'
        ).prefetch_related(
            'order__items__menu_item__category' # Added category to prefetch
        ).get(pk=sale_id)
    except Sale.DoesNotExist:
        return HttpResponse("Sale not found.", status=404)

    # --- NEW: Determine the section from the order's items ---
    section_name = "General Sale" # A safe default
    first_item = sale.order.items.first()
    if first_item:
        # Get the "display" name of the module, e.g., "Kitchen" or "Bar"
        section_name = first_item.menu_item.category.get_module_display()

    context = {
        'sale': sale,
        'order': sale.order,
        'receipt_title': 'Customer Receipt',
        'section_name': section_name, # Pass the section name to the template
    }
    return render(request, 'pos/print_customer_receipt.html', context)


@login_required
def htmx_live_order_tickets(request, section):
    section_name = section.capitalize()
    pending_orders = Order.objects.filter(
        status=Order.Status.PENDING,
        items__menu_item__category__module=section_name
    ).distinct().order_by('created_at').prefetch_related('items__menu_item__category')
    for order in pending_orders:
        order.age_minutes = int((timezone.now() - order.created_at).total_seconds() / 60)
    context = {'orders': pending_orders, 'module_type': section_name}
    return render(request, 'pos/partials/_live_order_tickets.html', context)


@login_required
def htmx_awaiting_payment_list(request, section):
    section_name = section.capitalize()
    ready_orders = Order.objects.filter(
        status=Order.Status.READY,
        items__menu_item__category__module=section_name
    ).distinct().order_by('-updated_at')
    context = {'orders': ready_orders}
    return render(request, 'pos/partials/_awaiting_payment_list.html', context)


@login_required
def order_list(request):
    """
    Displays a paginated and filterable list of all Orders with status-based coloring
    """
    queryset = Order.objects.select_related(
        'customer', 'table', 'waiter'
    ).prefetch_related(
        'items__menu_item'
    ).annotate(
        item_count=Count('items'),
        status_order=Case(
            When(status=Order.Status.PENDING, then=1),
            When(status=Order.Status.READY, then=2),
            When(status=Order.Status.COMPLETED, then=3),
            When(status=Order.Status.CANCELLED, then=4),
            default=5,
            output_field=IntegerField()
        )
    ).order_by('-created_at', 'status_order')

    # --- Filtering Parameters ---
    status_filter = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    search_query = request.GET.get('q', '').strip()
    waiter_filter = request.GET.get('waiter', '')

    # --- Apply Filters ---
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)

    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)

    if search_query:
        queryset = queryset.filter(
            Q(customer__name__icontains=search_query) |
            Q(table__table_number__icontains=search_query) |
            Q(id__icontains=search_query)
        )

    if waiter_filter:
        queryset = queryset.filter(waiter_id=waiter_filter)

    # --- Pagination ---
    paginator = Paginator(queryset, 25)  # 25 orders per page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'status_choices': Order.Status.choices,
        'waiters': User.objects.filter(role='waiter'),
        'selected_status': status_filter,
        'date_from': date_from,
        'date_to': date_to,
        'search_query': search_query,
        'selected_waiter': waiter_filter,
    }

    if request.htmx:
        return render(request, 'pos/partials/_order_table.html', context)

    return render(request, 'pos/order_list.html', context)


@login_required
def order_detail(request, pk):
    """
    Detailed view of an order with status change handling
    """
    order = get_object_or_404(
        Order.objects.select_related('customer', 'table', 'waiter')
        .prefetch_related('items__menu_item__category'),
        pk=pk
    )

    if request.method == 'POST' and request.htmx:
        new_status = request.POST.get('status')
        if new_status in dict(Order.Status.choices):
            order.status = new_status
            order.save()
            return JsonResponse({'success': True, 'new_status': order.get_status_display()})
        return JsonResponse({'error': 'Invalid status'}, status=400)

    context = {
        'order': order,
        'status_choices': Order.Status.choices,
    }
    return render(request, 'pos/order_detail.html', context)


def butchery_section_view(request):
    """
    Displays the list of butchery items and provides options to:
    1. Transfer to Kitchen/Grill (creates StockTransfer request - does not deduct stock)
    2. Sell to Walk-in Customer (quick sell on this page)
    Also shows the total kg transferred to Kitchen/Grill today, sales made today, and lists of those activities.
    """
    try:
        # Get all active butchery items
        butchery_items = MenuItem.objects.filter(
            is_active=True,
            category__module=Category.Module.BUTCHERY,
            selling_price__gt=0
        ).order_by('name')

        # Get Kitchen and Grill Staff for the transfer form
        kitchen_grill_staff = User.objects.filter(
            is_active=True,
            role__in=['kitchen_staff', 'grill_staff']  # Adjust roles if different in your User model
        ).order_by('first_name', 'last_name')

        today = timezone.now().date()

        # --- Calculate transfers for today (Butchery -> Kitchen OR Grill) ---
        transfers_today_queryset = StockTransfer.objects.filter(
            requested_from=StockTransfer.Section.BUTCHERY,
            requested_by_section__in=[StockTransfer.Section.KITCHEN, StockTransfer.Section.GRILL],
            request_timestamp__date=today
        ).select_related('menu_item', 'requested_by_user', 'transferred_to_user')

        total_transferred_today = transfers_today_queryset.aggregate(
            total_kg=Coalesce(Sum('quantity'), Decimal('0.000'), output_field=DecimalField())
        )['total_kg']

        transfers_today_list = transfers_today_queryset.order_by('-request_timestamp')

        # --- Calculate sales for today (Butchery items only) ---

        # 1. Find Order IDs that contain at least one Butchery item sold TODAY
        #    We need to link Sale -> Order -> OrderItem -> MenuItem (Butchery)
        #    Filter Sale by date first for efficiency.
        today_sale_ids = Sale.objects.filter(
            processed_at__date=today
        ).values_list('order_id', flat=True).distinct()

        # 2. Find OrderItem IDs for those orders that are Butchery items
        butchery_orderitem_ids = OrderItem.objects.filter(
            order_id__in=today_sale_ids,
            menu_item__category__module=Category.Module.BUTCHERY
        ).values_list('id', flat=True)

        # 3. Get the actual OrderItem queryset for display/details (annotated)
        raw_sales_today_list = OrderItem.objects.filter(
            id__in=butchery_orderitem_ids
        ).select_related(
            'menu_item',
            'order'  # Use 'order' to access the related Order object
        ).order_by('-order__sales__processed_at')[:20]  # Order by Sale processed time

        # --- Annotate the queryset with the calculated total price ---
        sales_today_list = raw_sales_today_list.annotate(
            calculated_total=F('quantity') * F('price_at_sale')
        )
        # --- END Annotate ---

        # --- Aggregate totals for summary stats ---
        #    a. Total quantity sold (sum of quantities from relevant OrderItems)
        total_quantity_sold_today_aggr = OrderItem.objects.filter(
            id__in=butchery_orderitem_ids
        ).aggregate(
            total_kg=Coalesce(Sum('quantity'), Decimal('0.000'), output_field=DecimalField())
        )
        total_quantity_sold_today = total_quantity_sold_today_aggr['total_kg']

        #    b. Total sales amount (sum of calculated totals from annotated queryset)
        #       This ensures consistency with what's shown in the itemized list.
        total_sales_today = sum(
            (item.calculated_total for item in sales_today_list),
            Decimal('0.00')
        )

        # Prepare Sale Payment Methods for Quick Sell Form
        available_payment_methods = [
            (method.value, method.label) for method in Sale.PaymentMethod
            if method != Sale.PaymentMethod.CREDIT
        ]

        # Prepare Destination Sections for Transfer Form
        destination_sections = [
            (StockTransfer.Section.KITCHEN.value, StockTransfer.Section.KITCHEN.label),
            (StockTransfer.Section.GRILL.value, StockTransfer.Section.GRILL.label)
        ]

        context = {
            'butchery_items': butchery_items,
            'kitchen_grill_staff': kitchen_grill_staff,
            'total_transferred_today': total_transferred_today,
            'transfers_today_list': transfers_today_list,

            # --- Sales data ---
            'total_sales_today': total_sales_today,
            'total_quantity_sold_today': total_quantity_sold_today,
            'sales_today_list': sales_today_list,
            # --- END Sales data ---

            'now': timezone.now(),
            'destination_sections': destination_sections,
            'sale_payment_methods': available_payment_methods,
        }
        return render(request, 'pos/butchery_section.html', context)

    except Exception as e:
        logger.error(f"Error in butchery_section_view: {e}", exc_info=True)
        messages.error(request, "An error occurred while loading the Butchery section.")
        # Fallback render or redirect
        return render(request, 'pos/butchery_section.html', {
            'butchery_items': [],
            'kitchen_grill_staff': [],
            'total_transferred_today': Decimal('0.000'),
            'transfers_today_list': [],
            'total_sales_today': Decimal('0.00'),
            'total_quantity_sold_today': Decimal('0.000'),
            'sales_today_list': [],
            'now': timezone.now(),
            'destination_sections': [],
            'sale_payment_methods': [],
        })


@login_required
def butchery_section_quick_sell_view(request):
    """
    Enhanced quick sale view with comprehensive HTMX response that updates multiple page sections.
    Handles a quick sale directly from the Butchery Section page without page refresh.
    1. Records the sale for the 'Walking In' customer.
    2. Deducts stock immediately.
    3. Creates an Order and OrderItem.
    4. Creates a corresponding Sale record with selected payment method.
    5. Marks the Order as COMPLETED.
    6. Returns dynamic updates for sales stats, recent sales list, and stock levels.
    Triggered via HTMX POST.
    """
    if request.method != 'POST' or not request.htmx:
        logger.warning("butchery_section_quick_sell_view: Invalid request method or not HTMX.")
        return JsonResponse({'success': False, 'message': 'Invalid request'}, status=400)

    try:
        # --- Get data from POST ---
        item_id_str = request.POST.get('item_id')
        quantity_str = request.POST.get('quantity')
        amount_str = request.POST.get('amount')
        payment_method_str = request.POST.get('payment_method')
        mpesa_code_str = request.POST.get('mpesa_code', '').strip()

        # --- Enhanced Validation ---
        if not item_id_str:
            return render(request, 'pos/partials/_error_message.html', {
                'error_message': 'Item ID is required.',
                'error_type': 'validation'
            })

        if not quantity_str and not amount_str:
            return render(request, 'pos/partials/_error_message.html', {
                'error_message': 'Please enter either quantity (kg) or amount (KES).',
                'error_type': 'validation'
            })

        if quantity_str and amount_str:
            return render(request, 'pos/partials/_error_message.html', {
                'error_message': 'Please enter only quantity (kg) OR amount (KES), not both.',
                'error_type': 'validation'
            })

        if not payment_method_str:
            return render(request, 'pos/partials/_error_message.html', {
                'error_message': 'Payment method is required.',
                'error_type': 'validation'
            })

        if payment_method_str not in [pm[0] for pm in Sale.PaymentMethod.choices]:
            return render(request, 'pos/partials/_error_message.html', {
                'error_message': 'Invalid payment method selected.',
                'error_type': 'validation'
            })

        if payment_method_str == Sale.PaymentMethod.MPESA and not mpesa_code_str:
            return render(request, 'pos/partials/_error_message.html', {
                'error_message': 'M-Pesa transaction code is required for M-Pesa payments.',
                'error_type': 'validation'
            })

        # --- Validate and get the MenuItem ---
        try:
            item_id = int(item_id_str)
        except (ValueError, TypeError):
            return render(request, 'pos/partials/_error_message.html', {
                'error_message': 'Invalid item ID provided.',
                'error_type': 'validation'
            })

        item = get_object_or_404(MenuItem, id=item_id, category__module=Category.Module.BUTCHERY, is_recipe=False)

        # --- Calculate final quantity from quantity OR amount ---
        quantity = Decimal('0.000')
        if quantity_str:
            try:
                quantity = Decimal(quantity_str)
                if quantity <= 0:
                    return render(request, 'pos/partials/_error_message.html', {
                        'error_message': 'Quantity must be greater than 0.',
                        'error_type': 'validation'
                    })
            except (InvalidOperation, ValueError):
                return render(request, 'pos/partials/_error_message.html', {
                    'error_message': 'Invalid quantity format.',
                    'error_type': 'validation'
                })
        elif amount_str:
            try:
                amount = Decimal(amount_str)
                if amount <= 0:
                    return render(request, 'pos/partials/_error_message.html', {
                        'error_message': 'Amount must be greater than 0.',
                        'error_type': 'validation'
                    })
                if item.selling_price <= 0:
                    return render(request, 'pos/partials/_error_message.html', {
                        'error_message': f'Item {item.name} has an invalid selling price for amount-based sale.',
                        'error_type': 'business_logic'
                    })
                quantity = (amount / item.selling_price).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
                if quantity <= 0:
                    return render(request, 'pos/partials/_error_message.html', {
                        'error_message': 'Calculated quantity is zero or negative.',
                        'error_type': 'calculation'
                    })
            except (InvalidOperation, ValueError, DivisionByZero):
                return render(request, 'pos/partials/_error_message.html', {
                    'error_message': 'Invalid amount format or calculation error.',
                    'error_type': 'validation'
                })

        # --- Check Stock Availability ---
        if item.stock_quantity is None:
            return render(request, 'pos/partials/_error_message.html', {
                'error_message': f'Stock not tracked for {item.name}.',
                'error_type': 'stock'
            })
        if item.stock_quantity < quantity:
            return render(request, 'pos/partials/_error_message.html', {
                'error_message': f'Insufficient stock for {item.name}. Available: {item.stock_quantity}kg',
                'error_type': 'stock'
            })

        # --- Get Walking In Customer ---
        try:
            walk_in_customer = Customer.objects.get(pk=1)  # Assuming pk=1 is Walking In
        except Customer.DoesNotExist:
            logger.error("Walking In customer (pk=1) not found.")
            return render(request, 'pos/partials/_error_message.html', {
                'error_message': 'System error: Default customer not found. Please contact support.',
                'error_type': 'system'
            })

        # --- Perform ALL actions Atomically ---
        try:
            with transaction.atomic():
                # 1. Deduct stock immediately
                original_stock = item.stock_quantity
                item.stock_quantity -= quantity
                item.save(update_fields=['stock_quantity'])
                logger.info(
                    f"Stock deducted for quick sale: {quantity} kg of {item.name}. New stock: {item.stock_quantity}")

                # 2. Create Order for Walking In customer
                line_total = quantity * item.selling_price
                order = Order.objects.create(
                    waiter=request.user,
                    customer=walk_in_customer,
                    table=None,  # Takeaway
                    subtotal=line_total.quantize(Decimal('0.01'))
                )
                logger.info(f"Order #{order.id} created for quick sale.")

                # 3. Create OrderItem
                order_item = OrderItem.objects.create(
                    order=order,
                    menu_item=item,
                    quantity=quantity,
                    price_at_sale=item.selling_price
                )
                logger.info(f"OrderItem #{order_item.id} created for Order #{order.id}.")

                # 4. Create Sale Record
                sale_data = {
                    'order': order,
                    'payment_method': payment_method_str,
                    'amount_paid': order.subtotal.quantize(Decimal('0.01')),
                }
                if payment_method_str == Sale.PaymentMethod.MPESA and mpesa_code_str:
                    sale_data['mpesa_transaction_id'] = mpesa_code_str

                sale = Sale.objects.create(**sale_data)
                logger.info(f"Sale #{sale.id} created for Order #{order.id}.")

                # 5. Mark Order as Completed
                order.status = Order.Status.COMPLETED
                order.save(update_fields=['status'])
                logger.info(f"Order #{order.id} marked as COMPLETED.")

            # --- Calculate Updated Sales Stats for Today ---
            today = timezone.now().date()

            # Get today's butchery sale IDs more efficiently
            today_sale_ids = Sale.objects.filter(
                processed_at__date=today
            ).values_list('order_id', flat=True).distinct()

            # Get butchery OrderItems for those sales
            butchery_orderitem_ids = OrderItem.objects.filter(
                order_id__in=today_sale_ids,
                menu_item__category__module=Category.Module.BUTCHERY
            ).values_list('id', flat=True)

            # Calculate updated totals
            totals_aggr = OrderItem.objects.filter(
                id__in=butchery_orderitem_ids
            ).aggregate(
                total_quantity=Coalesce(Sum('quantity'), Decimal('0.000'), output_field=DecimalField()),
                total_amount=Coalesce(Sum(F('quantity') * F('price_at_sale')), Decimal('0.00'),
                                      output_field=DecimalField())
            )

            updated_total_quantity_sold = totals_aggr['total_quantity']
            updated_total_sales = totals_aggr['total_amount']

            # --- Prepare Context for Dynamic Updates ---
            context = {
                'item_id': item.id,
                'item_name': item.name,
                'item': item,  # Add the full item object
                'quantity': quantity,
                'line_total': line_total.quantize(Decimal('0.01')),
                'payment_method': sale.get_payment_method_display(),
                'sale': sale,
                'order': order,
                'order_item': order_item,
                'updated_total_sales': updated_total_sales,
                'updated_total_quantity_sold': updated_total_quantity_sold,
                'original_stock': original_stock,
                'new_stock': item.stock_quantity,
            }

            # --- Return Dynamic Updates Template ---
            return render(request, 'pos/partials/_sale_success_updates.html', context)

        except IntegrityError as e:
            logger.error(f"Database Integrity Error creating Sale: {e}", exc_info=True)
            return render(request, 'pos/partials/_error_message.html', {
                'error_message': 'Database error occurred. Please try again.',
                'error_type': 'database',
                'debug_info': str(e) if settings.DEBUG else None
            })
        except ValidationError as e:
            logger.error(f"Validation Error creating Sale: {e}", exc_info=True)
            return render(request, 'pos/partials/_error_message.html', {
                'error_message': 'Invalid data provided. Please check your inputs.',
                'error_type': 'validation',
                'debug_info': str(e) if settings.DEBUG else None
            })

    except MenuItem.DoesNotExist:
        logger.error(f"Butchery item not found for ID: {item_id_str}")
        return render(request, 'pos/partials/_error_message.html', {
            'error_message': 'Item not found.',
            'error_type': 'not_found'
        })
    except Exception as e:
        logger.error(f"Unexpected error in butchery_section_quick_sell_view: {e}", exc_info=True)
        return render(request, 'pos/partials/_error_message.html', {
            'error_message': 'An unexpected error occurred. Please try again.',
            'error_type': 'system',
            'debug_info': str(e) if settings.DEBUG else None
        })


@login_required
def butchery_transfer_view(request):
    """
    Enhanced transfer view with better HTMX response and error handling.
    Handles the creation of a stock transfer *request* from Butchery to Kitchen/Grill.
    Allows transfer by quantity (kg) or amount (KES).
    NOW DEDUCTS MenuItem.stock_quantity immediately (like quick sale).
    Triggered via HTMX POST.
    Returns modern HTMX response with multiple page updates.
    """
    logger.info(f"butchery_transfer_view called by user {request.user}")

    # Check for POST method and HTMX
    if request.method != 'POST' or not request.htmx:
        error_msg = f"Invalid request method or not HTMX. Method: {request.method}, HTMX: {request.htmx}"
        logger.warning(error_msg)
        return render(request, 'pos/partials/_error_message.html', {
            'error_message': 'Invalid request method.',
            'error_type': 'method'
        })

    try:
        # Get and validate raw data
        raw_item_id = request.POST.get('item_id')
        raw_quantity = request.POST.get('quantity')
        raw_amount = request.POST.get('amount')
        raw_destination_section = request.POST.get('destination_section')
        raw_transferred_to_user_id = request.POST.get('transferred_to_user')

        logger.debug(f"Raw data - item_id: {raw_item_id}, quantity: {raw_quantity}, amount: {raw_amount}")

        # Validation with user-friendly error messages
        if not raw_item_id:
            return render(request, 'pos/partials/_error_message.html', {
                'error_message': 'Item ID is required.',
                'error_type': 'validation'
            })
        if not raw_quantity and not raw_amount:
            return render(request, 'pos/partials/_error_message.html', {
                'error_message': 'Please enter either quantity (kg) or amount (KES).',
                'error_type': 'validation'
            })
        if raw_quantity and raw_amount:
            return render(request, 'pos/partials/_error_message.html', {
                'error_message': 'Please enter only quantity (kg) OR amount (KES), not both.',
                'error_type': 'validation'
            })
        if not raw_destination_section:
            return render(request, 'pos/partials/_error_message.html', {
                'error_message': 'Destination section is required.',
                'error_type': 'validation'
            })

        # Data Conversion and Validation
        try:
            item_id = int(raw_item_id)
        except (ValueError, TypeError) as e:
            return render(request, 'pos/partials/_error_message.html', {
                'error_message': 'Invalid item ID provided.',
                'error_type': 'validation'
            })

        item = get_object_or_404(MenuItem, id=item_id, category__module=Category.Module.BUTCHERY)

        quantity = Decimal('0.000')
        if raw_quantity:
            try:
                quantity = Decimal(raw_quantity)
                if quantity <= 0:
                    return render(request, 'pos/partials/_error_message.html', {
                        'error_message': 'Quantity must be greater than 0.',
                        'error_type': 'validation'
                    })
            except (InvalidOperation, ValueError):
                return render(request, 'pos/partials/_error_message.html', {
                    'error_message': 'Invalid quantity format.',
                    'error_type': 'validation'
                })
        elif raw_amount:
            try:
                amount = Decimal(raw_amount)
                if amount <= 0:
                    return render(request, 'pos/partials/_error_message.html', {
                        'error_message': 'Amount must be greater than 0.',
                        'error_type': 'validation'
                    })
                if item.selling_price <= 0:
                    return render(request, 'pos/partials/_error_message.html', {
                        'error_message': f'Item {item.name} has an invalid selling price for amount-based transfer.',
                        'error_type': 'business_logic'
                    })
                quantity = (amount / item.selling_price).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
                if quantity <= 0:
                    return render(request, 'pos/partials/_error_message.html', {
                        'error_message': 'Calculated quantity is zero or negative.',
                        'error_type': 'calculation'
                    })
            except (InvalidOperation, ValueError, DivisionByZero):
                return render(request, 'pos/partials/_error_message.html', {
                    'error_message': 'Invalid amount format or calculation error.',
                    'error_type': 'validation'
                })

        # Validate destination section
        if raw_destination_section not in [StockTransfer.Section.KITCHEN, StockTransfer.Section.GRILL]:
            return render(request, 'pos/partials/_error_message.html', {
                'error_message': 'Invalid destination section provided.',
                'error_type': 'validation'
            })
        destination_section = raw_destination_section

        # Validate and get transferred_to_user
        transferred_to_user = None
        if raw_transferred_to_user_id:
            try:
                uuid.UUID(raw_transferred_to_user_id)
                transferred_to_user = User.objects.get(id=raw_transferred_to_user_id, is_active=True)
            except (ValueError, User.DoesNotExist):
                logger.warning(f"Invalid or non-existent user ID: {raw_transferred_to_user_id}")
                # Continue without assigned user

        # Check Stock Availability
        if item.stock_quantity is None:
            return render(request, 'pos/partials/_error_message.html', {
                'error_message': f'Stock not tracked for {item.name}.',
                'error_type': 'stock'
            })
        if item.stock_quantity < quantity:
            return render(request, 'pos/partials/_error_message.html', {
                'error_message': f'Insufficient stock for {item.name}. Available: {item.stock_quantity}kg',
                'error_type': 'stock'
            })

        # --- Perform ALL actions Atomically (like quick sale) ---
        try:
            with transaction.atomic():
                # 1. Deduct stock immediately (NEW - like quick sale)
                original_stock = item.stock_quantity
                item.stock_quantity -= quantity
                item.save(update_fields=['stock_quantity'])
                logger.info(
                    f"Stock deducted for transfer: {quantity} kg of {item.name}. New stock: {item.stock_quantity}")

                # 2. Create Stock Transfer Request Record
                stock_transfer_object = StockTransfer.objects.create(
                    menu_item=item,
                    quantity=quantity,
                    requested_from=StockTransfer.Section.BUTCHERY,
                    requested_by_section=destination_section,
                    requested_by_user=request.user,
                    transferred_to_user=transferred_to_user,
                )
                logger.info(f"Stock transfer #{stock_transfer_object.id} created.")

            # Calculate Updated Total for Today
            today = timezone.now().date()
            updated_total = StockTransfer.objects.filter(
                requested_from=StockTransfer.Section.BUTCHERY,
                requested_by_section__in=[StockTransfer.Section.KITCHEN, StockTransfer.Section.GRILL],
                request_timestamp__date=today
            ).aggregate(
                total=Sum('quantity')
            )['total'] or Decimal('0.000')

            # Prepare Context for Dynamic Updates
            context = {
                'item_id': item.id,
                'item_name': item.name,
                'item': item,  # Add the full item object for stock updates
                'quantity': quantity,
                'destination_section': stock_transfer_object.get_requested_by_section_display(),
                'transferred_to_user_name': transferred_to_user.get_full_name() if transferred_to_user else "Any Staff",
                'new_transfer': stock_transfer_object,
                'updated_total': updated_total,
                'original_stock': original_stock,  # Add for stock update display
                'new_stock': item.stock_quantity,  # Add for stock update display
            }

            return render(request, 'pos/partials/_transfer_success_updates.html', context)

        except IntegrityError as e:
            logger.error(f"Database Integrity Error creating Stock Transfer: {e}", exc_info=True)
            return render(request, 'pos/partials/_error_message.html', {
                'error_message': 'Database error occurred. Please try again.',
                'error_type': 'database',
                'debug_info': str(e) if settings.DEBUG else None
            })
        except ValidationError as e:
            logger.error(f"Validation Error creating Stock Transfer: {e}", exc_info=True)
            return render(request, 'pos/partials/_error_message.html', {
                'error_message': 'Invalid data provided. Please check your inputs.',
                'error_type': 'validation',
                'debug_info': str(e) if settings.DEBUG else None
            })

    except MenuItem.DoesNotExist:
        logger.error(f"Butchery item not found for ID: {raw_item_id}")
        return render(request, 'pos/partials/_error_message.html', {
            'error_message': 'Item not found.',
            'error_type': 'not_found'
        })
    except Exception as e:
        logger.error(f"Unexpected error in butchery_transfer_view: {e}", exc_info=True)
        return render(request, 'pos/partials/_error_message.html', {
            'error_message': 'An unexpected error occurred. Please try again.',
            'error_type': 'system',
            'debug_info': str(e) if settings.DEBUG else None
        })

@login_required  # Should be protected by a 'butcher' or 'cashier' role decorator
def butchery_pos_view(request):
    """
    Renders a dedicated Point of Sale screen for the Butchery to sell
    raw goods directly to external customers.
    """
    # All sales from this screen are to the default "Walking In" customer.
    walk_in_customer, _ = Customer.objects.get_or_create(pk=1, defaults={'name': 'Walking In'})

    # We pre-populate the form with this customer and no table.
    form = OrderCreationForm(initial={'customer': walk_in_customer, 'table': None})

    # We only fetch sellable items assigned to the 'Butchery' module.
    butchery_items = MenuItem.objects.filter(
        is_active=True,
        category__module=Category.Module.BUTCHERY,
        selling_price__gt=0,
        is_recipe=False  # A butchery only sells raw goods
    ).order_by('name')

    # We use the same session cart logic as the main POS.
    table_session = get_table_session(request)

    context = {
        'form': form,
        'menu_items': butchery_items,
        'cart': table_session.get('butchery_cart', {'items': {}, 'total': 0.0}),
        'module': 'Butchery',  # This is used by the cart partial
        'form_title': 'Butchery Point of Sale',
        'finalize_url_name': 'pos:finalize_butchery_order',  # A dedicated URL for submission
    }
    return render(request, 'pos/butchery_pos.html', context)



@login_required
def finalize_butchery_order(request):
    """
    Finalizes an order from the Butchery POS and redirects to the correct
    station view for payment processing.
    """
    if request.method != 'POST':
        logger.warning("finalize_butchery_order: Non-POST request received.")
        return redirect('pos:butchery_pos')

    # --- Debugging: Log session contents ---
    logger.debug(f"finalize_butchery_order called by user: {request.user}")
    table_session_raw = request.session.get('table_session', {})
    logger.debug(f"Raw table_session: {json.dumps(table_session_raw, indent=2, default=str)}")
    # --- End Debugging ---

    # Get the cart from the session
    table_session = get_table_session(request)  # Use util function if it handles session structure
    # Alternatively: table_session = request.session.get('table_session', {})

    # --- Debugging: Log retrieved table_session and specific cart ---
    logger.debug(f"Retrieved table_session (via util or direct): {json.dumps(table_session, indent=2, default=str)}")
    # --- End Debugging ---

    # Use the correct session cart key for Butchery
    cart = table_session.get('butchery_cart', {})

    # --- Debugging: Log the specific butchery_cart contents ---
    logger.debug(f"Retrieved butchery_cart: {json.dumps(cart, indent=2, default=str)}")
    logger.debug(
        f"Checking cart emptiness: cart={bool(cart)}, cart.get('items')={cart.get('items')}, bool(cart.get('items'))={bool(cart.get('items'))}")
    # --- End Debugging ---

    # Check if the cart is empty
    # Ensure cart exists, has an 'items' key, and that 'items' is not empty
    if not cart or not cart.get('items'):  # This is the line triggering the error
        error_msg = "Cannot create an empty order."
        logger.warning(f"finalize_butchery_order: {error_msg} for user {request.user}. Cart contents: {cart}")
        messages.error(request, error_msg)
        return redirect('pos:butchery_pos')  # Or return an error response for HTMX if applicable

    try:
        with transaction.atomic():
            # Get the default "Walking In" customer (assuming pk=1 is correct)
            walk_in_customer = Customer.objects.get(pk=1)

            # Create the Order object
            # Assuming no table for butchery sales (takeaway)
            order = Order.objects.create(
                waiter=request.user,
                customer=walk_in_customer,
                table=None,  # Butchery sales are always takeaway
                # Use the total directly from the session cart to avoid rounding issues
                subtotal=Decimal(str(cart.get('total', '0.00'))).quantize(Decimal('0.01'))
            )
            logger.info(f"Created new Butchery Order #{order.id}")

            # Create the OrderItem objects from the cart
            order_items_to_create = []
            for item_id_str, data in cart['items'].items():
                try:
                    item_id = int(item_id_str)
                    quantity = data.get('quantity', 0)
                    price_str = data.get('price', '0.00')

                    if quantity > 0 and price_str not in (None, '', '0.00'):  # Basic sanity check
                        order_items_to_create.append(OrderItem(
                            order=order,
                            menu_item_id=item_id,
                            quantity=quantity,
                            price_at_sale=Decimal(str(price_str))  # Ensure Decimal conversion
                        ))
                        logger.debug(f"Prepared OrderItem: Menu Item ID {item_id}, Qty {quantity}, Price {price_str}")
                except (ValueError, TypeError, InvalidOperation) as e:
                    logger.error(f"Error preparing OrderItem from cart data {data}: {e}")
                    # Optionally, add a message or skip the item
                    continue

            if not order_items_to_create:
                logger.error("No valid items found in cart to create OrderItems.")
                raise ValueError("Cart items could not be processed.")

            OrderItem.objects.bulk_create(order_items_to_create)
            logger.info(f"Created {len(order_items_to_create)} OrderItems for Order #{order.id}")

            # --- IMPORTANT: Clear the butchery cart after successful order creation ---
            # Check if 'butchery_cart' key exists in the session before deleting
            if 'table_session' in request.session and 'butchery_cart' in request.session['table_session']:
                logger.debug("Clearing 'butchery_cart' from session.")
                del request.session['table_session']['butchery_cart']
                request.session.modified = True  # MUST set this to True after modifying nested session data
            else:
                logger.warning("'butchery_cart' key not found in session['table_session'] during cleanup.")

        messages.success(request, f"Order #{order.id} created and ready for payment.")

        # Redirect to the unified station view (e.g., kitchen for payment processing)
        # Adjust 'kitchen' if payment happens elsewhere
        return redirect('pos:unified_station_view', section='kitchen')

    except Customer.DoesNotExist:
        logger.error("Walking In customer (pk=1) does not exist.")
        messages.error(request, "System error: Default customer not found.")
        return redirect('pos:butchery_pos')
    except Exception as e:
        logger.exception(f"Error finalizing butchery order for user {request.user}: {e}")
        messages.error(request, f"An error occurred while creating the order: {e}")
        return redirect('pos:butchery_pos')  # Or return an error response for HTMX if applicable

# @login_required (should be kitchen staff, manager, etc.)
def stock_request_create_view(request):
    """
    Allows Kitchen staff to create a new stock requisition from the Butchery.
    """
    if request.method == 'POST':
        item_id = request.POST.get('menu_item')
        quantity = request.POST.get('quantity')

        if not item_id or not quantity or Decimal(quantity) <= 0:
            messages.error(request, "Please select a valid item and quantity.")
        else:
            StockTransfer.objects.create(
                menu_item_id=item_id,
                quantity=Decimal(quantity),
                requested_from=StockTransfer.Section.BUTCHERY,
                requested_by_section=StockTransfer.Section.KITCHEN,
                requested_by_user=request.user
            )
            messages.success(request, "Stock request sent to Butchery successfully.")
            return redirect('pos:stock_request_list')

    # The form will show only raw materials available from the butchery
    butchery_ingredients = MenuItem.objects.filter(is_recipe=False, category__module=Category.Module.BUTCHERY)
    context = {
        'form_title': 'Request Stock from Butchery',
        'form_items': butchery_ingredients,
    }
    return render(request, 'pos/stock_request_form.html', context)


# @login_required (should be butcher, manager)
def stock_request_list_view(request):
    """
    Displays a list of all stock transfer requests for fulfillment.
    """
    # Show pending requests at the top
    pending_requests = StockTransfer.objects.filter(status=StockTransfer.Status.REQUESTED).order_by('request_timestamp')
    fulfilled_requests = StockTransfer.objects.filter(status=StockTransfer.Status.FULFILLED).order_by(
        '-fulfillment_timestamp')[:20]

    context = {
        'pending_requests': pending_requests,
        'fulfilled_requests': fulfilled_requests,
    }
    return render(request, 'pos/stock_request_list.html', context)


# @login_required (should be butcher, manager)
def fulfill_stock_request_view(request, pk):
    """
    Marks a stock request as fulfilled and adjusts inventory levels.
    """
    stock_request = get_object_or_404(StockTransfer, pk=pk, status=StockTransfer.Status.REQUESTED)

    if request.method == 'POST':
        ingredient = stock_request.menu_item
        if ingredient.stock_quantity < stock_request.quantity:
            messages.error(request, f"Cannot fulfill request. Insufficient stock for {ingredient.name}.")
            return redirect('pos:stock_request_list')

        with transaction.atomic():
            # Decrease the stock from the Butchery's inventory
            ingredient.stock_quantity -= stock_request.quantity
            ingredient.save()

            # Update the request status
            stock_request.status = StockTransfer.Status.FULFILLED
            stock_request.fulfilled_by_user = request.user
            stock_request.fulfillment_timestamp = timezone.now()
            stock_request.save()

            messages.success(request, "Stock request fulfilled successfully.")
        return redirect('pos:stock_request_list')

    # This should not be accessed via GET, but redirect just in case
    return redirect('pos:stock_request_list')


class PurchaseOrderCreateView(View):
    """
    View for creating a new purchase order with its items.
    """
    template_name = 'pos/purchase_order_form.html'

    def get(self, request, *args, **kwargs):
        form = PurchaseOrderForm()
        formset = PurchaseOrderItemFormSet(queryset=PurchaseOrderItem.objects.none())
        context = {
            'form': form,
            'formset': formset,
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        form = PurchaseOrderForm(request.POST)
        formset = PurchaseOrderItemFormSet(request.POST)

        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    # Save the purchase order first
                    purchase_order = form.save(commit=False)
                    purchase_order.created_by = request.user
                    purchase_order.save()

                    # Then save the items
                    instances = formset.save(commit=False)
                    for instance in instances:
                        instance.purchase_order = purchase_order
                        instance.save()

                    messages.success(request, 'Purchase order created successfully!')
                    return redirect(reverse('pos:purchase_order_detail', kwargs={'pk': purchase_order.pk}))

            except Exception as e:
                messages.error(request, f'Error creating purchase order: {str(e)}')

        context = {
            'form': form,
            'formset': formset,
        }
        return render(request, self.template_name, context)


class PurchaseOrderDetailView(View):
    """
    View for viewing a purchase order and its items.
    """
    template_name = 'pos/purchase_order_detail.html'

    def get(self, request, pk, *args, **kwargs):
        purchase_order = get_object_or_404(PurchaseOrder, pk=pk)
        items = purchase_order.items.all()

        context = {
            'purchase_order': purchase_order,
            'items': items,
        }
        return render(request, self.template_name, context)


@login_required
@admin_manager_required
def pos(request):
    """
    Gathers all necessary data and renders the main Admin Dashboard homepage.
    """
    today = timezone.now().date()
    start_of_day = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
    end_of_day = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.max.time()))

    # --- 1. Key Performance Indicators (KPIs) for Today ---
    sales_today = Sale.objects.filter(processed_at__range=(start_of_day, end_of_day))
    total_sales = sales_today.aggregate(total=Sum('amount_paid'))['total'] or 0
    total_orders = sales_today.count()
    average_sale = total_sales / total_orders if total_orders > 0 else 0

    # Find the top selling item for today
    top_selling_item = OrderItem.objects.filter(
        order__sales__in=sales_today
    ).values('menu_item__name').annotate(
        total_sold=Sum('quantity')
    ).order_by('-total_sold').first()

    kpi_data = {
        'total_sales': total_sales,
        'total_orders': total_orders,
        'average_sale': average_sale,
        'top_selling_item': top_selling_item['menu_item__name'] if top_selling_item else "N/A"
    }

    # --- 2. Sales Data for the Last 7 Days Chart ---
    sales_chart_data = []
    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        daily_sales = Sale.objects.filter(processed_at__date=date).aggregate(total=Sum('amount_paid'))['total'] or 0
        sales_chart_data.append({
            'day': date.strftime('%a'),  # Mon, Tue, etc.
            'sales': float(daily_sales)
        })

    # --- 3. Draft Purchase Orders ---
    draft_purchase_orders = PurchaseOrder.objects.filter(
        status=PurchaseOrder.Status.DRAFT
    ).select_related('supplier', 'created_by').prefetch_related(
        'items__menu_item'
    ).order_by('-order_date')
    for po in draft_purchase_orders:
        po.total_cost = sum(item.total_cost for item in po.items.all())

    # --- 4. Alerts and Table Status ---
    active_alerts = StockAlert.objects.filter(status=StockAlert.Status.ACTIVE)
    tables = Table.objects.filter(is_active=True).order_by('table_number')

    # --- 5. NEW: Duplicate Menu Items Detection (WITH CACHING) ---
    cache_key = 'dashboard_duplicate_stats'
    duplicate_stats = cache.get(cache_key)
    if duplicate_stats is None:
        duplicate_stats = MenuItem.get_duplicate_stats()
        cache.set(cache_key, duplicate_stats, 600)  # Cache for 10 minutes

    dashboard_duplicates = duplicate_stats['groups'][:3]
    has_more_duplicates = len(duplicate_stats['groups']) > 3

    context = {
        'kpi_data': kpi_data,
        'sales_chart_data': json.dumps(sales_chart_data),
        'active_alerts': active_alerts,
        'draft_purchase_orders': draft_purchase_orders,
        'tables': tables,
        'duplicate_stats': duplicate_stats,
        'dashboard_duplicates': dashboard_duplicates,
        'has_more_duplicates': has_more_duplicates,
    }
    return render(request, 'pos/admin_dashboard.html', context)


@login_required
@admin_manager_required
def clear_duplicate_cache(request):
    if request.method == "POST":
        cache.delete('dashboard_duplicate_stats')
        messages.success(request, "Duplicate detection cache cleared. Next load will re-scan.")
    return redirect('pos:pos')
# Additional views for duplicate management
@login_required
@admin_manager_required
def duplicate_menu_items_view(request):
    """Full duplicate management page"""
    duplicate_stats = MenuItem.get_duplicate_stats()

    context = {
        'duplicate_stats': duplicate_stats,
        'duplicate_groups': duplicate_stats['groups']
    }

    return render(request, 'pos/duplicate_menu_items.html', context)



@login_required
@admin_manager_required
@require_POST
def bulk_manage_duplicates(request):
    action = request.POST.get('action')
    item_ids = request.POST.getlist('item_ids')
    if not item_ids:
        messages.error(request, "No items selected")
        return redirect('pos:duplicate_menu_items')

    items = MenuItem.objects.filter(id__in=item_ids)

    if action == 'deactivate':
        items.update(is_active=False)
        messages.success(request, f"Deactivated {items.count()} items")

    elif action == 'delete':
        # ❌ NEVER allow deletion of used items — just deactivate
        items.update(is_active=False)
        messages.success(request, f"Deactivated {items.count()} items (safe alternative to delete)")

    elif action == 'merge':
        if items.count() < 2:
            messages.error(request, "Need at least 2 items to merge")
            return redirect('pos:duplicate_menu_items')
        primary = items.first()
        others = items.exclude(id=primary.id)

        # Merge stock
        total_stock = primary.stock_quantity + sum(o.stock_quantity for o in others)
        primary.stock_quantity = total_stock
        primary.save()

        # ✅ Deactivate (don’t delete) duplicates
        others.update(is_active=False)
        messages.success(request, f"Merged {others.count() + 1} items into '{primary.name}' (duplicates deactivated)")

    return redirect('pos:duplicate_menu_items')

@login_required
@admin_manager_required
@require_POST
def dismiss_all_dashboard_duplicates(request):
    """Hide all duplicate groups from dashboard view"""
    request.session['hide_dashboard_duplicates'] = True
    return JsonResponse({'success': True})

@login_required
@admin_manager_required
@require_POST
def toggle_menu_item_active(request, item_id):
    """
    Toggle the is_active status of a menu item via AJAX.
    """
    item = get_object_or_404(MenuItem, id=item_id)
    item.is_active = not item.is_active
    item.save(update_fields=['is_active'])
    status = "activated" if item.is_active else "deactivated"
    return JsonResponse({
        'success': True,
        'is_active': item.is_active,
        'message': f"'{item.name}' has been {status}."
    })

@login_required
@admin_manager_required
@require_POST
def edit_menu_item_ajax(request, item_id):
    """Quick edit menu item via AJAX"""
    item = get_object_or_404(MenuItem, id=item_id)
    if request.method == 'POST':
        try:
            # ✅ Convert string inputs to Decimal BEFORE assignment
            item.name = request.POST.get('name', item.name)

            selling_price = request.POST.get('selling_price')
            if selling_price:
                item.selling_price = Decimal(selling_price)

            supplier_cost_price = request.POST.get('supplier_cost_price')
            if supplier_cost_price:
                item.supplier_cost_price = Decimal(supplier_cost_price)

            stock_quantity = request.POST.get('stock_quantity')
            if stock_quantity:
                item.stock_quantity = Decimal(stock_quantity)

            # Now call clean() — all fields are Decimals
            item.clean()
            item.save()
            return JsonResponse({'success': True, 'message': 'Item updated successfully'})

        except (InvalidOperation, ValueError) as e:
            return JsonResponse({'success': False, 'errors': f'Invalid number format: {str(e)}'})
        except ValidationError as e:
            return JsonResponse({'success': False, 'errors': str(e)})

    # Optional: handle GET if needed
    return JsonResponse({
        'success': True,
        'item': {
            'id': item.id,
            'name': item.name,
            'selling_price': str(item.selling_price),
            'supplier_cost_price': str(item.supplier_cost_price),
            'stock_quantity': str(item.stock_quantity),
            'is_active': item.is_active
        }
    })


@login_required
@admin_manager_required
@require_POST
def dismiss_duplicate_group(request, group_index):
    """Temporarily dismiss a duplicate group from dashboard view"""
    # Store dismissed groups in session
    dismissed_groups = request.session.get('dismissed_duplicate_groups', [])
    if group_index not in dismissed_groups:
        dismissed_groups.append(group_index)
        request.session['dismissed_duplicate_groups'] = dismissed_groups

    return JsonResponse({'success': True})

@login_required
@require_POST
def dismiss_alert(request, alert_id):
    """
    Dismiss a specific stock alert.
    """
    alert = get_object_or_404(StockAlert, id=alert_id, status=StockAlert.Status.ACTIVE)

    alert.status = StockAlert.Status.DISMISSED
    alert.dismissed_by = request.user
    alert.dismissed_at = timezone.now()
    alert.save()

    if request.headers.get('Content-Type') == 'application/json':
        return JsonResponse({'success': True, 'message': 'Alert dismissed successfully'})
    else:
        messages.success(request, f'Alert for {alert.menu_item.name} has been dismissed.')
        return redirect('pos:admin_dashboard')


@login_required
@require_POST
def dismiss_all_alerts(request):
    """
    Dismiss all active stock alerts.
    """
    active_alerts = StockAlert.objects.filter(status=StockAlert.Status.ACTIVE)
    count = active_alerts.count()

    active_alerts.update(
        status=StockAlert.Status.DISMISSED,
        dismissed_by=request.user,
        dismissed_at=timezone.now()
    )

    if request.headers.get('Content-Type') == 'application/json':
        return JsonResponse({'success': True, 'message': f'{count} alerts dismissed successfully'})
    else:
        messages.success(request, f'{count} alerts have been dismissed.')
        return redirect('pos:admin_dashboard')


@login_required
@admin_manager_required
@require_POST
def approve_purchase_order(request, po_id):
    """
    Approve a draft purchase order and change status to pending
    """
    try:
        with transaction.atomic():
            po = get_object_or_404(PurchaseOrder, id=po_id, status=PurchaseOrder.Status.DRAFT)
            po.status = PurchaseOrder.Status.PENDING
            po.save()

            message = f'Purchase Order #{po.id} approved and sent to {po.supplier.name}'

            if request.headers.get('Content-Type') == 'application/json':
                return JsonResponse({
                    'success': True,
                    'message': message
                })
            else:
                messages.success(request, message)
                return redirect('pos:admin_dashboard')

    except Exception as e:
        error_message = f'Error approving purchase order: {str(e)}'
        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({
                'success': False,
                'message': error_message
            })
        else:
            messages.error(request, error_message)
            return redirect('pos:admin_dashboard')


@login_required
@admin_manager_required
@require_POST
def dismiss_purchase_order(request, po_id):
    """
    Dismiss (delete) a draft purchase order
    """
    try:
        with transaction.atomic():
            po = get_object_or_404(PurchaseOrder, id=po_id, status=PurchaseOrder.Status.DRAFT)
            po_number = po.id
            supplier_name = po.supplier.name
            po.delete()

            message = f'Purchase Order #{po_number} for {supplier_name} has been dismissed'

            if request.headers.get('Content-Type') == 'application/json':
                return JsonResponse({
                    'success': True,
                    'message': message
                })
            else:
                messages.success(request, message)
                return redirect('pos:admin_dashboard')

    except Exception as e:
        error_message = f'Error dismissing purchase order: {str(e)}'
        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({
                'success': False,
                'message': error_message
            })
        else:
            messages.error(request, error_message)
            return redirect('pos:admin_dashboard')


@login_required
@admin_manager_required
@require_POST
def approve_all_purchase_orders(request):
    """
    Approve all draft purchase orders and change status to pending
    """
    try:
        with transaction.atomic():
            draft_pos = PurchaseOrder.objects.filter(status=PurchaseOrder.Status.DRAFT)
            approved_count = draft_pos.update(status=PurchaseOrder.Status.PENDING)

            message = f'{approved_count} purchase orders approved and sent to suppliers'

            if request.headers.get('Content-Type') == 'application/json':
                return JsonResponse({
                    'success': True,
                    'approved_count': approved_count,
                    'message': message
                })
            else:
                messages.success(request, message)
                return redirect('pos:admin_dashboard')

    except Exception as e:
        error_message = f'Error approving purchase orders: {str(e)}'
        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({
                'success': False,
                'message': error_message
            })
        else:
            messages.error(request, error_message)
            return redirect('pos:admin_dashboard')


@login_required
@admin_manager_required
@require_POST
def dismiss_all_purchase_orders(request):
    """
    Dismiss (delete) all draft purchase orders
    """
    try:
        with transaction.atomic():
            draft_pos = PurchaseOrder.objects.filter(status=PurchaseOrder.Status.DRAFT)
            dismissed_count = draft_pos.count()
            draft_pos.delete()

            message = f'{dismissed_count} draft purchase orders have been dismissed'

            if request.headers.get('Content-Type') == 'application/json':
                return JsonResponse({
                    'success': True,
                    'dismissed_count': dismissed_count,
                    'message': message
                })
            else:
                messages.success(request, message)
                return redirect('pos:admin_dashboard')

    except Exception as e:
        error_message = f'Error dismissing purchase orders: {str(e)}'
        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({
                'success': False,
                'message': error_message
            })
        else:
            messages.error(request, error_message)
            return redirect('pos:admin_dashboard')

@login_required
def htmx_merged_payment_modal(request):
    """
    Gathers all selected orders and renders the unified payment terminal
    with the combined data.
    """
    if request.method != 'POST':
        return redirect('pos:waiter_dashboard')

    order_ids = request.POST.getlist('order_ids')
    if not order_ids:
        messages.error(request, "No orders were selected for payment.")
        return redirect('pos:waiter_dashboard')

    # Fetch all selected orders that belong to the current waiter
    orders_to_pay = Order.objects.filter(
        id__in=order_ids,
        waiter=request.user
    ).prefetch_related('items__menu_item', 'customer')

    if len(order_ids) != orders_to_pay.count():
        messages.error(request, "Some selected orders could not be found or do not belong to you.")
        return redirect('pos:waiter_dashboard')

    # Calculate the combined total
    grand_total = sum(order.total_amount for order in orders_to_pay)

    # For merged bills, we assume a single customer (from the first order) for loyalty checks,
    # but we will disable the discount forms to avoid complexity.
    primary_customer = orders_to_pay.first().customer

    context = {
        'orders_to_pay': orders_to_pay,  # Pass the list of orders
        'order': orders_to_pay.first(),  # Pass the first order for customer/table context
        'grand_total': grand_total,
        'is_merged_bill': True,  # A flag to tell the template this is a merged bill
        'payment_methods': Sale.PaymentMethod.choices,
        'loyalty_settings': LoyaltySettings.objects.first(),
        'primary_customer': primary_customer,
    }

    # We will render the SAME payment screen partial used for single orders
    return render(request, 'pos/partials/_payment_screen.html', context)


@login_required
def process_merged_payment(request):
    """
    Processes a single payment that covers multiple selected orders.
    """
    if request.method != 'POST':
        return redirect('pos:waiter_dashboard')

    order_ids = request.POST.getlist('order_ids')
    payment_method = request.POST.get('payment_method')
    amount_paid_str = request.POST.get('amount_paid')

    # --- This view now uses the same reliable message-based system for printing/alerts ---
    try:
        with transaction.atomic():
            orders_to_pay = Order.objects.filter(id__in=order_ids)

            # Create one single Sale for this entire transaction
            sale = Sale.objects.create(
                payment_method=payment_method,
                amount_paid=Decimal(amount_paid_str)
            )

            # Link all the paid orders to this single sale
            sale.orders.set(orders_to_pay)

            # Mark all associated orders as completed
            orders_to_pay.update(status=Order.Status.COMPLETED)

            # Free up all unique tables associated with these orders
            table_ids = orders_to_pay.exclude(table__isnull=True).values_list('table_id', flat=True).distinct()
            Table.objects.filter(id__in=table_ids).update(status=Table.Status.AVAILABLE)

            messages.success(request, f"Successfully processed merged payment for {len(order_ids)} orders.")

            # We don't need to trigger printing/alerts for a merged payment,
            # but you could add that logic here if desired.

            return redirect('pos:waiter_dashboard')

    except Exception as e:
        messages.error(request, f"An error occurred: {str(e)}")
        return redirect('pos:waiter_dashboard')


@login_required
@ensure_csrf_cookie
def table_layout_editor_view(request):
    """Render drag-and-drop layout editor with table + open orders."""
    # Cache key for frequently accessed data
    cache_key = f"table_layout_data_{request.user.id}"
    cached_data = cache.get(cache_key)

    if not cached_data:
        open_statuses = [Order.Status.PENDING, Order.Status.READY]
        open_orders_prefetch = Prefetch(
            'orders',
            queryset=Order.objects.filter(status__in=open_statuses)
            .prefetch_related('items__menu_item', 'waiter')
            .order_by('created_at'),
            to_attr='open_orders'
        )

        tables = Table.objects.filter(is_active=True).prefetch_related(
            open_orders_prefetch
        ).order_by('table_number')

        # Calculate total bill for each table
        for table in tables:
            table.total_bill = sum(order.total_amount for order in table.open_orders)

        # Cache for 5 minutes
        cache.set(cache_key, tables, 300)
        cached_data = tables

    # Calculate statistics correctly
    total_tables = len(cached_data)
    busy_tables = sum(1 for table in cached_data if table.open_orders)
    available_tables = total_tables - busy_tables

    return render(request, 'pos/table_layout_editor.html', {
        'tables': cached_data,
        'total_tables': total_tables,
        'busy_tables': busy_tables,
        'available_tables': available_tables,
    })


@login_required
@require_POST
def save_table_layout_view(request):
    """Save updated table positions from layout editor."""
    try:
        if not request.body:
            return JsonResponse({
                'success': False,
                'message': 'No data received.'
            }, status=400)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error in save_table_layout_view: {e}")
            return JsonResponse({
                'success': False,
                'message': f'Invalid JSON: {e}'
            }, status=400)

        positions = data.get('positions', [])
        if not positions:
            return JsonResponse({
                'success': False,
                'message': 'No positions to save.'
            }, status=400)

        # Validate positions data
        for pos in positions:
            if not pos.get('id'):
                return JsonResponse({
                    'success': False,
                    'message': 'Invalid position data: missing table ID.'
                }, status=400)

            # Validate coordinates are numeric and within reasonable bounds
            try:
                x = float(pos.get('x', 0))
                y = float(pos.get('y', 0))
                if x < 0 or y < 0 or x > 2000 or y > 2000:  # Reasonable bounds
                    raise ValueError("Coordinates out of bounds")
            except (ValueError, TypeError):
                return JsonResponse({
                    'success': False,
                    'message': 'Invalid position data: coordinates must be numeric and within bounds.'
                }, status=400)

        # Save positions in a transaction
        with transaction.atomic():
            updated_count = 0
            for pos in positions:
                table_id = pos.get('id')
                if not table_id:
                    continue

                x = int(float(pos.get('x', 0)))
                y = int(float(pos.get('y', 0)))

                # Update only if the table exists and is active
                updated = Table.objects.filter(
                    pk=table_id,
                    is_active=True
                ).update(position_x=x, position_y=y)

                updated_count += updated

        # Clear cache after successful update
        cache_key = f"table_layout_data_{request.user.id}"
        cache.delete(cache_key)

        if updated_count > 0:
            return HttpResponse(
                f'<div class="notification is-success is-light mt-4">Layout saved successfully! Updated {updated_count} table(s).</div>'
            )
        else:
            return HttpResponse(
                '<div class="notification is-warning is-light mt-4">No tables were updated.</div>'
            )

    except Exception as e:
        logger.error(f"Error in save_table_layout_view: {e}")
        return HttpResponse(
            f'<div class="notification is-danger is-light mt-4">Error: {e}</div>',
            status=500
        )


# Optional: Add a view to reset table positions
@login_required
@require_POST
def reset_table_layout_view(request):
    """Reset all table positions to default."""
    try:
        with transaction.atomic():
            updated_count = Table.objects.filter(is_active=True).update(
                position_x=0,
                position_y=0
            )

        # Clear cache
        cache_key = f"table_layout_data_{request.user.id}"
        cache.delete(cache_key)

        return HttpResponse(
            f'<div class="notification is-success is-light mt-4">Layout reset successfully! Reset {updated_count} table(s).</div>'
        )
    except Exception as e:
        logger.error(f"Error in reset_table_layout_view: {e}")
        return HttpResponse(
            f'<div class="notification is-danger is-light mt-4">Error: {e}</div>',
            status=500
        )


@login_required
def add_items_to_order_view(request, order_id):
    """
    Prepares the order creation screen to add more items to an
    existing, pending order.
    """
    order = get_object_or_404(
        Order.objects.select_related('table', 'customer'),
        pk=order_id,
        waiter=request.user,
        status=Order.Status.PENDING  # Can only add to pending orders
    )

    # Determine the section of the existing order (Kitchen or Bar)
    # This will be used to lock the interface to only show relevant items.
    first_item = order.items.first()
    if not first_item:
        # This should rarely happen, but it's a safe fallback
        messages.error(request, "Cannot add items to an empty order.")
        return redirect('pos:table_detail', table_id=order.table.id)

    locked_section = first_item.menu_item.category.module

    # Pre-fill the form with the existing order's details
    form = OrderCreationForm(initial={'customer': order.customer, 'table': order.table})

    # Fetch the menu items and categories for the locked section
    initial_categories = Category.objects.filter(module=locked_section).order_by('name')
    initial_menu_items = MenuItem.objects.filter(
        is_active=True, category__module=locked_section, selling_price__gt=0
    ).order_by('name')

    context = {
        'form': form,
        'sections': [(locked_section, locked_section)],  # Only show the one relevant section
        'kitchen_cart': get_table_session(request)['kitchen_cart'],
        'bar_cart': get_table_session(request)['bar_cart'],
        'active_module': locked_section,
        'initial_categories': initial_categories,
        'initial_menu_items': initial_menu_items,

        # --- These new context variables tell the template it's in "add mode" ---
        'existing_order': order,
        'locked_section': locked_section,
    }

    # We reuse the same powerful create_order.html template
    return render(request, 'pos/create_order.html', context)


@login_required
def htmx_multi_payment_modal(request, order_id):
    """
    Renders the multi-payment terminal for an order.
    """
    order = get_object_or_404(Order.objects.select_related('customer'), pk=order_id)

    # Clear any previous discount data from the session
    for key in ['loyalty_redemption', 'coupon_redemption']:
        request.session.pop(key, None)
    request.session.modified = True

    context = {
        'order': order,
        'payment_methods': Sale.PaymentMethod.choices,
        'loyalty_settings': LoyaltySettings.objects.first(),
    }

    return render(request, 'pos/partials/_multi_payment_screen.html', context)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def process_multi_payment(request, order_id, data=None):
    """
    Process multiple payments for a single order with automatic leaderboard recalculation.

    This view handles orders paid with multiple payment methods (e.g., Cash + Mpesa + Credit).
    After successful payment, it triggers dynamic leaderboard bonus recalculation so that
    waiter rankings and bonuses update immediately.

    Expected JSON payload:
    {
        "payments": [
            {
                "method": "Cash",
                "amount": 1500.00,
                "mpesa_code": null
            },
            {
                "method": "Mpesa",
                "amount": 1000.00,
                "mpesa_code": "ABC123XYZ"
            },
            {
                "method": "Credit",
                "amount": 500.00,
                "mpesa_code": null
            }
        ]
    }

    Args:
        request: Django request object
        order_id: Primary key of the Order being paid
        data: Optional pre-parsed data dict (for internal calls)

    Returns:
        JsonResponse with success/error status and payment details
    """

    # Fetch the order with related data
    order = get_object_or_404(
        Order.objects.select_related('customer', 'table', 'waiter')
        .prefetch_related('items__menu_item__category'),
        pk=order_id
    )

    try:
        # Parse payment data from request body or use provided data
        if data is None:
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({
                    'error': 'Invalid JSON data',
                    'details': 'Request body must be valid JSON'
                }, status=400)

        payments_data = data.get('payments', [])

        if not payments_data:
            return JsonResponse({
                'error': 'No payments provided',
                'details': 'The "payments" array is empty or missing'
            }, status=400)

        # ===================================================================
        # STEP 1: VALIDATE ALL PAYMENT DATA
        # ===================================================================

        validated_payments = []
        total_payment_amount = Decimal('0.00')
        valid_methods = [choice[0] for choice in Sale.PaymentMethod.choices]

        for i, payment_data in enumerate(payments_data):
            method = payment_data.get('method', '').strip()
            amount_str = str(payment_data.get('amount', '0')).strip()
            mpesa_code = payment_data.get('mpesa_code', '').strip() if payment_data.get('mpesa_code') else None

            # Validate payment method
            if method not in valid_methods:
                return JsonResponse({
                    'error': f'Invalid payment method in payment {i + 1}',
                    'details': f'"{method}" is not a valid payment method. Valid methods: {", ".join(valid_methods)}'
                }, status=400)

            # Validate and parse amount
            try:
                amount = Decimal(amount_str)
                if amount <= 0:
                    return JsonResponse({
                        'error': f'Invalid amount in payment {i + 1}',
                        'details': 'Amount must be greater than 0'
                    }, status=400)
            except (ValueError, Decimal.InvalidOperation):
                return JsonResponse({
                    'error': f'Invalid amount format in payment {i + 1}',
                    'details': f'Cannot parse "{amount_str}" as a valid number'
                }, status=400)

            # Validate M-Pesa code if required
            if method == 'Mpesa' and not mpesa_code:
                return JsonResponse({
                    'error': f'M-Pesa transaction code required for payment {i + 1}',
                    'details': 'mpesa_code field is required when payment method is Mpesa'
                }, status=400)

            # Add to validated payments list
            validated_payments.append({
                'method': method,
                'amount': amount,
                'mpesa_code': mpesa_code
            })
            total_payment_amount += amount

        # ===================================================================
        # STEP 2: CALCULATE FINAL TOTAL WITH DISCOUNTS
        # ===================================================================

        # Get discount data from session
        loyalty_redemption = request.session.get('loyalty_redemption', {})
        coupon_redemption = request.session.get('coupon_redemption', {})

        loyalty_discount = Decimal(str(loyalty_redemption.get('discount', '0.00')))
        coupon_discount = Decimal(str(coupon_redemption.get('discount', '0.00')))

        # Calculate final total due after discounts
        final_total_due = max(
            order.total_amount - loyalty_discount - coupon_discount,
            Decimal('0.00')
        )

        # ===================================================================
        # STEP 3: VALIDATE PAYMENT AMOUNT
        # ===================================================================

        if total_payment_amount < final_total_due:
            shortage = final_total_due - total_payment_amount
            return JsonResponse({
                'error': 'Insufficient payment',
                'details': f'Total payment ({total_payment_amount:.2f} KES) is less than amount due ({final_total_due:.2f} KES)',
                'shortage': float(shortage)
            }, status=400)

        # ===================================================================
        # STEP 4: VALIDATE CREDIT PAYMENTS
        # ===================================================================

        customer = order.customer
        credit_amount = sum(p['amount'] for p in validated_payments if p['method'] == 'Credit')

        if credit_amount > 0:
            # Check if customer can use credit
            if customer.id == 1:  # Walk-in customer (assuming ID 1)
                return JsonResponse({
                    'error': 'Credit not available for walk-in customers',
                    'details': 'Walk-in customers must pay with Cash or Mpesa'
                }, status=400)

            # Check credit limit
            if customer.credit_balance + credit_amount > customer.credit_limit:
                available_credit = customer.credit_limit - customer.credit_balance
                return JsonResponse({
                    'error': 'Credit limit would be exceeded',
                    'details': f'Customer has {available_credit:.2f} KES available credit. Attempted to charge {credit_amount:.2f} KES',
                    'current_balance': float(customer.credit_balance),
                    'credit_limit': float(customer.credit_limit),
                    'available_credit': float(available_credit)
                }, status=400)

        # ===================================================================
        # STEP 5: PROCESS THE PAYMENT
        # ===================================================================

        change_due = max(total_payment_amount - final_total_due, Decimal('0.00'))

        try:
            with transaction.atomic():
                # 5.1: Update customer credit balance if credit was used
                if credit_amount > 0:
                    customer.credit_balance += credit_amount
                    customer.save(update_fields=['credit_balance'])
                    logger.info(
                        f"Updated credit balance for {customer.name}: +{credit_amount} KES (new balance: {customer.credit_balance} KES)")

                # 5.2: Create individual sale records for each payment
                sale_records = []
                for payment in validated_payments:
                    sale = Sale.objects.create(
                        order=order,
                        payment_method=payment['method'],
                        amount_paid=payment['amount'],
                        mpesa_transaction_id=payment['mpesa_code'],
                        processed_at=timezone.now()
                    )
                    sale_records.append(sale)
                    logger.info(
                        f"Created Sale #{sale.id}: {payment['method']} - {payment['amount']} KES "
                        f"{'(Code: ' + payment['mpesa_code'] + ')' if payment['mpesa_code'] else ''}"
                    )

                # 5.3: Mark order as completed
                order.status = Order.Status.COMPLETED
                order.save(update_fields=['status'])
                logger.info(f"Order #{order.id} marked as COMPLETED")

                # 5.4: Process stock updates and generate low-stock alerts
                low_stock_items = process_stock_updates(order)
                if low_stock_items:
                    logger.warning(f"Low stock alerts generated for: {', '.join(low_stock_items)}")

                # 5.5: Handle customer loyalty points
                loyalty_settings = LoyaltySettings.objects.first()
                if loyalty_settings and loyalty_settings.is_active and hasattr(customer, 'loyalty_points'):
                    # Calculate points earned from this order
                    points_earned = math.floor(
                        order.total_amount / loyalty_settings.points_per_kes
                    ) if loyalty_settings.points_per_kes > 0 else 0

                    # Subtract redeemed points
                    points_redeemed = loyalty_redemption.get('points', 0)

                    # Update customer loyalty points
                    customer.loyalty_points += (points_earned - points_redeemed)
                    customer.save(update_fields=['loyalty_points'])

                    logger.info(
                        f"Loyalty points for {customer.name}: "
                        f"+{points_earned} earned, -{points_redeemed} redeemed "
                        f"(new total: {customer.loyalty_points})"
                    )

                # 5.6: Award waiter base reward points (NOT including leaderboard bonus)
                waiter_reward_settings = WaiterRewardSettings.objects.first()
                waiter = order.waiter

                if waiter_reward_settings and waiter_reward_settings.is_active and hasattr(waiter,
                                                                                           'waiter_reward_points'):
                    # Calculate base points earned (bonus is calculated separately by leaderboard)
                    waiter_points_earned = math.floor(
                        order.total_amount / waiter_reward_settings.points_per_kes
                    ) if waiter_reward_settings.points_per_kes > 0 else 0

                    if waiter_points_earned > 0:
                        # Add base points to waiter's total
                        # NOTE: Leaderboard bonus is managed separately by signals
                        waiter.waiter_reward_points += waiter_points_earned
                        waiter.save(update_fields=['waiter_reward_points'])

                        logger.info(
                            f"Waiter '{waiter.get_full_name()}' earned {waiter_points_earned} "
                            f"base points from Order #{order.id} (new total: {waiter.waiter_reward_points})"
                        )

                # 5.7: Handle coupon usage
                if coupon_id := coupon_redemption.get('id'):
                    Coupon.objects.filter(id=coupon_id).update(times_used=F('times_used') + 1)
                    logger.info(f"Coupon #{coupon_id} usage count incremented")

                # 5.8: Update table status if applicable
                if order.table:
                    # Check if there are any other pending/ready orders for this table
                    other_orders_exist = Order.objects.filter(
                        table=order.table,
                        status__in=[Order.Status.PENDING, Order.Status.READY]
                    ).exclude(pk=order.id).exists()

                    if not other_orders_exist:
                        # No other orders - mark table as available
                        order.table.status = Table.Status.AVAILABLE
                        order.table.save(update_fields=['status'])
                        logger.info(f"Table {order.table.table_number} marked as AVAILABLE")

                # 5.9: Clear session discount data
                for key in ['loyalty_redemption', 'coupon_redemption']:
                    request.session.pop(key, None)
                request.session.modified = True

                # ===================================================================
                # STEP 6: PREPARE SUCCESS RESPONSE
                # ===================================================================

                payment_summary = []
                for payment in validated_payments:
                    summary = f"{payment['method']}: {payment['amount']:.2f} KES"
                    if payment['mpesa_code']:
                        summary += f" (Code: {payment['mpesa_code']})"
                    payment_summary.append(summary)

                response_data = {
                    'success': True,
                    'message': f'Order #{order.id} completed successfully!',
                    'order_id': order.id,
                    'order_number': str(order.id),
                    'total_due': float(final_total_due),
                    'total_paid': float(total_payment_amount),
                    'change_due': float(change_due),
                    'payment_summary': payment_summary,
                    'sale_ids': [sale.id for sale in sale_records],
                    'payment_count': len(sale_records),
                    'timestamp': timezone.now().isoformat()
                }

                # Add low stock alerts to response if any
                if low_stock_items:
                    response_data['low_stock_alerts'] = low_stock_items
                    response_data['low_stock_count'] = len(low_stock_items)

                    alert_message = f"\n\nLow-stock alerts created for: {', '.join(low_stock_items[:3])}"
                    if len(low_stock_items) > 3:
                        alert_message += f" and {len(low_stock_items) - 3} more"
                    alert_message += "."

                    response_data['message'] += alert_message

                # Add discount details if any were applied
                if loyalty_discount > 0 or coupon_discount > 0:
                    response_data['discounts_applied'] = {
                        'loyalty_discount': float(loyalty_discount),
                        'coupon_discount': float(coupon_discount),
                        'total_discount': float(loyalty_discount + coupon_discount)
                    }

            # ===================================================================
            # STEP 7: TRIGGER LEADERBOARD RECALCULATION (OUTSIDE TRANSACTION)
            # ===================================================================
            # This is the CRITICAL part for dynamic bonuses!
            # After the payment completes, recalculate all waiter positions
            # and update their bonuses immediately.

            try:
                from pos.signals import recalculate_all_leaderboard_bonuses
                recalculate_all_leaderboard_bonuses()
                logger.info("🏆 Leaderboard recalculated after multi-payment")
            except Exception as leaderboard_error:
                # Don't fail the payment if leaderboard update fails
                logger.error(f"⚠️ Leaderboard recalculation failed: {leaderboard_error}")
                logger.error(traceback.format_exc())

            # Return success response
            return JsonResponse(response_data)

        except IntegrityError as e:
            logger.error(f"❌ Database integrity error during multi-payment: {str(e)}")
            logger.error(traceback.format_exc())
            return JsonResponse({
                'error': 'Database error',
                'details': 'A database constraint was violated. Please try again.',
                'technical_details': str(e) if settings.DEBUG else None
            }, status=500)

        except Exception as e:
            logger.error(f"❌ Multi-payment processing error: {str(e)}")
            logger.error(traceback.format_exc())
            return JsonResponse({
                'error': 'Server error',
                'details': f'An unexpected error occurred: {str(e)}',
                'traceback': traceback.format_exc() if settings.DEBUG else None
            }, status=500)

    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON decode error: {str(e)}")
        return JsonResponse({
            'error': 'Invalid JSON data',
            'details': str(e)
        }, status=400)

    except Exception as e:
        logger.error(f"❌ Unexpected outer error: {str(e)}")
        logger.error(traceback.format_exc())
        return JsonResponse({
            'error': 'Unexpected error',
            'details': f'An unexpected error occurred: {str(e)}',
            'traceback': traceback.format_exc() if settings.DEBUG else None
        }, status=500)


def process_stock_updates(order):
    """
    Process stock updates and create low-stock alerts.
    Returns list of items that triggered low-stock alerts.
    """
    low_stock_items = []

    def get_section_from_category(menu_item):
        mapping = {
            Category.Module.KITCHEN: PurchaseOrder.Section.KITCHEN,
            Category.Module.BAR: PurchaseOrder.Section.BAR,
            Category.Module.BUTCHERY: PurchaseOrder.Section.BUTCHERY,
        }
        return mapping.get(menu_item.category.module, PurchaseOrder.Section.KITCHEN)

    def get_or_create_draft_purchase_order(supplier, section):
        admin_user = User.objects.filter(role='admin').first() or User.objects.filter(is_superuser=True).first()
        draft_po, created = PurchaseOrder.objects.get_or_create(
            supplier=supplier,
            status=PurchaseOrder.Status.DRAFT,
            requested_for_section=section,
            defaults={
                'created_by': admin_user,
                'notes': f"Auto-generated on {timezone.now():%Y-%m-%d %H:%M}",
            }
        )
        return draft_po

    def add_item_to_purchase_order(po, menu_item, qty):
        try:
            line, created = PurchaseOrderItem.objects.get_or_create(
                purchase_order=po,
                menu_item=menu_item,
                defaults={
                    'quantity_ordered': qty,
                    'unit_price': menu_item.supplier_cost_price or Decimal('0.00'),
                }
            )
            if not created:
                line.quantity_ordered += qty
                line.save(update_fields=['quantity_ordered'])
        except Exception as e:
            print(f"⚠️ Error saving PO item for {menu_item.name}: {e}")

    for item in order.items.select_related('menu_item__category').prefetch_related(
            'menu_item__recipe_items__ingredient'):
        menu_item = item.menu_item

        if menu_item.is_recipe:
            # Handle recipe items
            for recipe_line in menu_item.recipe_items.all():
                ingredient = recipe_line.ingredient
                qty_used = item.quantity * recipe_line.quantity

                # Update stock
                db_ing = MenuItem.objects.select_for_update().get(pk=ingredient.pk)
                db_ing.stock_quantity -= qty_used
                db_ing.save(update_fields=['stock_quantity'])

                # Check for low stock
                if (db_ing.low_stock_threshold > 0 and
                        db_ing.stock_quantity <= db_ing.low_stock_threshold and
                        not StockAlert.objects.filter(menu_item=db_ing, status=StockAlert.Status.ACTIVE).exists()):

                    StockAlert.objects.create(
                        menu_item=db_ing,
                        stock_level_at_alert=db_ing.stock_quantity
                    )
                    low_stock_items.append(db_ing.name)

                    # Auto-create PO if supplier and reorder quantity are set
                    if db_ing.preferred_supplier and db_ing.reorder_quantity > 0:
                        section = get_section_from_category(db_ing)
                        po = get_or_create_draft_purchase_order(db_ing.preferred_supplier, section)
                        add_item_to_purchase_order(po, db_ing, db_ing.reorder_quantity)

        else:
            # Handle regular items
            db_item = MenuItem.objects.select_for_update().get(pk=menu_item.pk)
            db_item.stock_quantity -= item.quantity
            db_item.save(update_fields=['stock_quantity'])

            # Check for low stock
            if (db_item.low_stock_threshold > 0 and
                    db_item.stock_quantity <= db_item.low_stock_threshold and
                    not StockAlert.objects.filter(menu_item=db_item, status=StockAlert.Status.ACTIVE).exists()):

                StockAlert.objects.create(
                    menu_item=db_item,
                    stock_level_at_alert=db_item.stock_quantity
                )
                low_stock_items.append(db_item.name)

                # Auto-create PO if supplier and reorder quantity are set
                if db_item.preferred_supplier and db_item.reorder_quantity > 0:
                    section = get_section_from_category(db_item)
                    po = get_or_create_draft_purchase_order(db_item.preferred_supplier, section)
                    add_item_to_purchase_order(po, db_item, db_item.reorder_quantity)

    return low_stock_items


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def add_single_payment(request, order_id):
    """
    Add a single payment to an order (for incremental payment building).
    This allows building payments one by one before final completion.
    """
    order = get_object_or_404(Order.objects.select_related('customer'), pk=order_id)

    try:
        data = json.loads(request.body)
        method = data.get('method', '').strip()
        amount_str = str(data.get('amount', '0')).strip()
        mpesa_code = data.get('mpesa_code', '').strip() if data.get('mpesa_code') else None

        # Validate inputs
        valid_methods = [choice[0] for choice in Sale.PaymentMethod.choices]
        if method not in valid_methods:
            return JsonResponse({'error': f'Invalid payment method: {method}'}, status=400)

        try:
            amount = Decimal(amount_str)
            if amount <= 0:
                return JsonResponse({'error': 'Amount must be greater than 0'}, status=400)
        except:
            return JsonResponse({'error': f'Invalid amount format: {amount_str}'}, status=400)

        if method == 'Mpesa' and not mpesa_code:
            return JsonResponse({'error': 'M-Pesa transaction code is required'}, status=400)

        # Validate credit limits for credit payments
        if method == 'Credit':
            customer = order.customer
            if customer.id == 1:
                return JsonResponse({'error': 'Credit not available for walk-in customers'}, status=400)

            # Get existing pending credit payments for this order
            existing_credit = Sale.objects.filter(
                order=order,
                payment_method='Credit',
                processed_at__isnull=True  # Assuming pending payments have null processed_at
            ).aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00')

            total_credit = existing_credit + amount
            if customer.credit_balance + total_credit > customer.credit_limit:
                return JsonResponse({'error': 'Credit limit would be exceeded'}, status=400)

        # Create a pending payment record (you might want to add a 'pending' status to Sale model)
        # Or store in session temporarily

        # For now, let's store pending payments in session
        pending_payments = request.session.get('pending_payments', {})
        order_payments = pending_payments.get(str(order_id), [])

        payment_data = {
            'id': len(order_payments) + 1,
            'method': method,
            'amount': float(amount),
            'mpesa_code': mpesa_code,
            'timestamp': timezone.now().isoformat()
        }

        order_payments.append(payment_data)
        pending_payments[str(order_id)] = order_payments
        request.session['pending_payments'] = pending_payments
        request.session.modified = True

        # Calculate totals
        total_pending = sum(p['amount'] for p in order_payments)

        # Get order total with discounts
        loyalty_redemption = request.session.get('loyalty_redemption', {})
        coupon_redemption = request.session.get('coupon_redemption', {})
        loyalty_discount = Decimal(str(loyalty_redemption.get('discount', '0.00')))
        coupon_discount = Decimal(str(coupon_redemption.get('discount', '0.00')))
        final_total_due = max(order.total_amount - loyalty_discount - coupon_discount, Decimal('0.00'))

        remaining = max(float(final_total_due) - total_pending, 0)

        return JsonResponse({
            'success': True,
            'payment': payment_data,
            'total_pending': total_pending,
            'total_due': float(final_total_due),
            'remaining': remaining,
            'can_complete': remaining <= 0.01
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        print(f"❌ Add payment error: {str(e)}")
        traceback.print_exc()
        return JsonResponse({'error': f'Server error: {str(e)}'}, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def remove_pending_payment(request, order_id):
    """
    Remove a pending payment from the session.
    """
    try:
        data = json.loads(request.body)
        payment_id = data.get('payment_id')

        pending_payments = request.session.get('pending_payments', {})
        order_payments = pending_payments.get(str(order_id), [])

        # Remove the payment
        order_payments = [p for p in order_payments if p['id'] != payment_id]

        if order_payments:
            pending_payments[str(order_id)] = order_payments
        else:
            pending_payments.pop(str(order_id), None)

        request.session['pending_payments'] = pending_payments
        request.session.modified = True

        # Calculate new totals
        total_pending = sum(p['amount'] for p in order_payments)

        # Get order total with discounts
        order = get_object_or_404(Order, pk=order_id)
        loyalty_redemption = request.session.get('loyalty_redemption', {})
        coupon_redemption = request.session.get('coupon_redemption', {})
        loyalty_discount = Decimal(str(loyalty_redemption.get('discount', '0.00')))
        coupon_discount = Decimal(str(coupon_redemption.get('discount', '0.00')))
        final_total_due = max(order.total_amount - loyalty_discount - coupon_discount, Decimal('0.00'))

        remaining = max(float(final_total_due) - total_pending, 0)

        return JsonResponse({
            'success': True,
            'total_pending': total_pending,
            'total_due': float(final_total_due),
            'remaining': remaining,
            'can_complete': remaining <= 0.01
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Server error: {str(e)}'}, status=500)



@login_required
@csrf_exempt
@require_http_methods(["POST"])
def complete_multi_payment_order(request, order_id):
    """
    Complete the order using all pending payments from session.
    """
    pending_payments = request.session.get('pending_payments', {})
    order_payments = pending_payments.get(str(order_id), [])
    if not order_payments:
        return JsonResponse({'error': 'No pending payments found'}, status=400)

    # Convert session data to the format expected by process_multi_payment
    payments_data = []
    for payment in order_payments:
        payments_data.append({
            'method': payment['method'],
            'amount': payment['amount'],
            'mpesa_code': payment.get('mpesa_code')
        })

    # Pass data directly instead of modifying request
    response = process_multi_payment(
        request,
        order_id,
        data={'payments': payments_data}
    )

    # Clear pending payments on success
    if response.status_code == 200:
        pending_payments.pop(str(order_id), None)
        request.session['pending_payments'] = pending_payments
        request.session.modified = True

    return response


@login_required
def get_pending_payments(request, order_id):
    """
    Get pending payments for an order from session.
    """
    pending_payments = request.session.get('pending_payments', {})
    order_payments = pending_payments.get(str(order_id), [])

    # Get order total with discounts for calculations
    order = get_object_or_404(Order, pk=order_id)
    loyalty_redemption = request.session.get('loyalty_redemption', {})
    coupon_redemption = request.session.get('coupon_redemption', {})
    loyalty_discount = Decimal(str(loyalty_redemption.get('discount', '0.00')))
    coupon_discount = Decimal(str(coupon_redemption.get('discount', '0.00')))
    final_total_due = max(order.total_amount - loyalty_discount - coupon_discount, Decimal('0.00'))

    total_pending = sum(p['amount'] for p in order_payments)
    remaining = max(float(final_total_due) - total_pending, 0)

    return JsonResponse({
        'payments': order_payments,
        'total_pending': total_pending,
        'total_due': float(final_total_due),
        'remaining': remaining,
        'can_complete': remaining <= 0.01
    })


from django.contrib.auth.decorators import user_passes_test
from django.utils.crypto import get_random_string


# ============================================================================
# AUTHORIZATION HELPERS
# ============================================================================

from django.contrib.auth.decorators import user_passes_test


def is_cashier(user):
    """Check if user has cashier role"""
    return user.is_authenticated and user.role in ['cashier', 'admin', 'manager']


cashier_required = user_passes_test(is_cashier, login_url='accounts:login')


def is_manager_or_admin(user):
    """Check if user has manager or admin role"""
    return user.is_authenticated and user.role in ['admin', 'manager']



manager_admin_required = user_passes_test(is_manager_or_admin, login_url='accounts:login')


# ============================================================================
# ORDER CANCELLATION WITH AUTHORIZATION
# ============================================================================

from django.utils.crypto import get_random_string


@login_required
@require_POST
def request_order_cancellation(request, order_id):
    """
    Waiter requests order cancellation - generates authorization code
    Stores in database for better reliability
    """
    order = get_object_or_404(
        Order.objects.select_related('table', 'waiter'),
        pk=order_id,
        waiter=request.user
    )

    # Check if order can be cancelled
    can_cancel_ready = not order.items.filter(menu_item__is_recipe=True).exists()

    if order.status == Order.Status.READY and not can_cancel_ready:
        return JsonResponse({
            'success': False,
            'message': 'Cannot cancel prepared food orders'
        })

    # Generate 6-digit authorization code
    auth_code = get_random_string(6, allowed_chars='0123456789')

    # Store in database
    order.cancellation_auth_code = auth_code
    order.cancellation_requested_at = timezone.now()
    order.cancellation_requested_by = request.user
    order.save(update_fields=[
        'cancellation_auth_code',
        'cancellation_requested_at',
        'cancellation_requested_by'
    ])

    # Log the request
    logger.info(
        f"Cancellation requested for Order #{order_id} by {request.user.get_full_name()}. "
        f"Auth code: {auth_code} (expires in 10 min)"
    )

    return JsonResponse({
        'success': True,
        'message': f'Cancellation requested. Auth code: {auth_code}',
        'auth_code': auth_code,
        'order_id': order_id,
        'expires_in': 600  # 10 minutes in seconds
    })


@login_required
@require_POST
def authorize_order_cancellation(request, order_id):
    """
    Manager/Admin authorizes order cancellation with code
    """
    if not is_manager_or_admin(request.user):
        return JsonResponse({
            'success': False,
            'message': 'Only managers and admins can authorize cancellations'
        }, status=403)

    order = get_object_or_404(Order, pk=order_id)
    auth_code = request.POST.get('auth_code', '').strip()

    # Check if there's a pending request
    if not order.cancellation_auth_code:
        return JsonResponse({
            'success': False,
            'message': 'No cancellation request found for this order'
        })

    # Check if code has expired (10 minutes)
    if order.cancellation_requested_at < timezone.now() - timedelta(minutes=10):
        # Clean up expired request
        order.cancellation_auth_code = None
        order.cancellation_requested_at = None
        order.cancellation_requested_by = None
        order.save(update_fields=[
            'cancellation_auth_code',
            'cancellation_requested_at',
            'cancellation_requested_by'
        ])
        return JsonResponse({
            'success': False,
            'message': 'Authorization code has expired'
        })

    # Verify code
    if auth_code != order.cancellation_auth_code:
        return JsonResponse({
            'success': False,
            'message': 'Invalid authorization code'
        })

    # Code is valid - proceed with cancellation
    try:
        with transaction.atomic():
            original_waiter = order.cancellation_requested_by
            table_id = order.table.id if order.table else None

            # Log the authorization
            logger.info(
                f"Order #{order_id} cancellation authorized by {request.user.get_full_name()} "
                f"(originally requested by {original_waiter.get_full_name() if original_waiter else 'Unknown'})"
            )

            # Cancel the order (or just mark as cancelled)
            order.status = Order.Status.CANCELLED
            order.save(update_fields=['status'])

            # Clear the authorization data
            order.cancellation_auth_code = None
            order.cancellation_requested_at = None
            order.cancellation_requested_by = None
            order.save(update_fields=[
                'cancellation_auth_code',
                'cancellation_requested_at',
                'cancellation_requested_by'
            ])

            return JsonResponse({
                'success': True,
                'message': f'Order #{order_id} cancelled successfully',
                'table_id': table_id,
                'authorized_by': request.user.get_full_name() or request.user.email
            })

    except Exception as e:
        logger.error(f"Error cancelling order: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)


@login_required
@cashier_required
def cashier_dashboard(request):
    """
    Shift-scoped cashier dashboard showing all READY orders from both Kitchen and Bar.
    Only accessible if cashier has an active shift.
    Stats are filtered to current shift's datetime range.
    """
    # Check if cashier has active shift
    shift = current_shift_for_user(request.user)
    if not shift:
        return render(request, 'schedule/no_shift.html', {})

    # Get shift datetime boundaries
    shift_start = shift.start_datetime
    shift_end = shift.end_datetime

    # Get all ready orders from both sections (within shift timeframe)
    ready_orders = Order.objects.filter(
        status=Order.Status.READY,
        created_at__gte=shift_start,
        created_at__lte=shift_end
    ).select_related(
        'customer', 'table', 'waiter'
    ).prefetch_related(
        'items__menu_item__category'
    ).order_by('updated_at')

    # Separate orders by section and count them
    bar_orders = []

    for order in ready_orders:
        first_item = order.items.first()
        if first_item:
            order.section = first_item.menu_item.category.module
            if order.section == Category.Module.BAR:
                bar_orders.append(order)
        else:
            order.section = 'Unknown'

    # Calculate shift-scoped stats (only sales during this shift)
    sales_in_shift = Sale.objects.filter(
        processed_at__gte=shift_start,
        processed_at__lte=shift_end
    )

    # NEW: Calculate how much cash each waiter should give at the end of the shift
    waiter_drops = Sale.objects.filter(
        processed_at__gte=shift_start,
        processed_at__lte=shift_end,
        payment_method=Sale.PaymentMethod.CASH
    ).values(
        'order__waiter__first_name', 
        'order__waiter__last_name',
        'order__waiter__email'
    ).annotate(
        total_cash=Sum('amount_paid')
    ).order_by('order__waiter__first_name')

    cashier_stats = {
        'orders_processed': sales_in_shift.count(),
        'total_collected': sales_in_shift.aggregate(
            total=Sum('amount_paid')
        )['total'] or Decimal('0.00'),
        'bar_orders_waiting': len(bar_orders),
    }

    context = {
        'shift': shift,
        'all_ready_orders': ready_orders,
        'waiter_drops': waiter_drops,
        'cashier_stats': cashier_stats,
        'now': timezone.now(),
    }

    return render(request, 'pos/cashier_dashboard.html', context)


@login_required
@staff_member_required
def htmx_customer_payment_modal(request, customer_id=None):
    """
    Renders a partial template for a quick customer debt payment modal.
    If customer_id is provided, sets it as the default.
    """
    if customer_id:
        customer = get_object_or_404(Customer, pk=customer_id)
        form = CustomerPaymentForm(initial={'customer': customer, 'amount_paid': customer.credit_balance})
    else:
        form = CustomerPaymentForm()
        # Filter dropdown to customers with debt
        form.fields['customer'].queryset = Customer.objects.filter(credit_balance__gt=0).order_by('name')

    context = {
        'form': form,
        'customer_id': customer_id,
    }
    return render(request, 'pos/partials/_customer_payment_modal.html', context)


@login_required
@staff_member_required
@require_POST
def htmx_process_customer_payment(request):
    """
    Processes a customer payment via HTMX and returns a success snackbar or refresh command.
    """
    form = CustomerPaymentForm(request.POST)
    if form.is_valid():
        try:
            with transaction.atomic():
                customer = form.cleaned_data['customer']
                amount_paid = form.cleaned_data['amount_paid']

                # Update balance
                customer.credit_balance -= amount_paid
                customer.save()

                # Create record
                payment = form.save(commit=False)
                payment.processed_by = request.user
                payment.save()

                # Return success message and trigger refresh on dashboard
                response = render(request, 'pos/partials/_payment_success_snack.html', {
                    'message': f"Collected {amount_paid} KES for {customer.name}. New Bal: {customer.credit_balance}"
                })
                response['HX-Trigger'] = json.dumps({"refreshDashboard": True, "closeModal": True})
                return response
        except Exception as e:
            return HttpResponse(f'<div class="text-red-600 font-bold p-2 bg-red-50 rounded">Error: {str(e)}</div>')
    
    # If invalid, return the form with errors
    return render(request, 'pos/partials/_customer_payment_modal.html', {'form': form})



@login_required
@admin_manager_required
def daily_stock_printout(request):
    """
    Generates a categorized list of all active menu items for physical stock auditing.
    """
    categories = Category.objects.prefetch_related(
        Prefetch('menu_items', queryset=MenuItem.objects.filter(is_active=True).order_by('name'))
    ).all().order_by('name')
    
    context = {
        'categories': categories,
        'print_time': timezone.now(),
    }
    return render(request, 'pos/stock_printout.html', context)


@login_required
@cashier_required
def htmx_refresh_cashier_orders(request):
    """
    HTMX endpoint to refresh the orders table.
    Returns just the table HTML.
    Also shift-scoped like the main dashboard.
    """
    # Check if cashier has active shift
    shift = current_shift_for_user(request.user)
    if not shift:
        # Return empty table if no shift
        context = {'all_ready_orders': []}
        return render(request, 'pos/partials/_cashier_orders_table_simple.html', context)

    # Get shift datetime boundaries
    shift_start = shift.start_datetime
    shift_end = shift.end_datetime

    # Get all ready orders (filtered by shift timeframe)
    ready_orders = Order.objects.filter(
        status=Order.Status.READY,
        created_at__gte=shift_start,
        created_at__lte=shift_end
    ).select_related(
        'customer', 'table', 'waiter'
    ).prefetch_related(
        'items__menu_item__category'
    ).order_by('updated_at')

    # Add section info
    for order in ready_orders:
        first_item = order.items.first()
        if first_item:
            order.section = first_item.menu_item.category.module
        else:
            order.section = 'Unknown'

    context = {
        'all_ready_orders': ready_orders,
    }

    return render(request, 'pos/partials/_cashier_orders_table_simple.html', context)


