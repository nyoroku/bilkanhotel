# views.py — Final, Corrected, Namespaced, and UX-Optimized
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum, Avg
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import (
    TripForm, InvoiceForm, PaymentForm, LogisticsFilterForm,
    DriverForm, TruckForm, DestinationForm, TransporterForm,
    ExpenseCategoryForm, CargoTypeForm, ExpenseForm, InvoiceCreditForm
)
from .models import (
    Trip, Invoice, Truck, Destination, Transporter, Driver, CargoType,
    FuelRecord, Expense, ExpenseCategory, Payment, InvoiceCredit,
)


# ------------------------------------------------------------------
# 1.  ORIGINAL  WORKING  VIEWS  (kept intact, with fixes)
# ------------------------------------------------------------------
@login_required
def logistics_report_view(request):
    """
    Main interactive Logistics Report using the unified Trip model
    """
    filter_form = LogisticsFilterForm(request.GET)
    today = timezone.now().date()
    start_date = request.GET.get('start_date') or (today - timedelta(days=30)).strftime('%Y-%m-%d')
    end_date = request.GET.get('end_date') or today.strftime('%Y-%m-%d')

    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        start_date = today - timedelta(days=30)
        end_date = today

    # base queryset – include trips with no actual_departure yet
    trips = Trip.objects.select_related(
        'truck', 'origin', 'destination', 'transporter'
    ).filter(
        Q(actual_departure__isnull=True) |
        Q(actual_departure__date__range=[start_date, end_date])
    )

    if filter_form.is_valid():
        cd = filter_form.cleaned_data
        if cd.get('status'):
            trips = trips.filter(status=cd['status'])
        if cd.get('transporter'):
            trips = trips.filter(transporter=cd['transporter'])
        if cd.get('destination'):
            trips = trips.filter(destination=cd['destination'])
        if cd.get('truck'):
            trips = trips.filter(truck=cd['truck'])
        if cd.get('search'):
            sq = cd['search']
            trips = trips.filter(
                Q(truck__truck_number__icontains=sq) |
                Q(transporter__name__icontains=sq) |
                Q(destination__name__icontains=sq) |
                Q(remarks__icontains=sq)
            )

    # ✅ FIXED: Replaced 'fuel_amount' with 'fuel_total_cost'
    totals = trips.aggregate(
        total_transport=Sum('transport_amount'),
        total_fuel=Sum('fuel_total_cost'),  # ← Changed from fuel_amount
        total_tonnage=Sum('weight_tons'),
        count=Count('id')
    )
    for k, v in totals.items():
        if 'total' in k:
            totals[k] = v or Decimal('0.00')
        else:
            totals[k] = v or 0

    paginator = Paginator(trips.order_by('-actual_departure', '-created_at'), 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    ctx = {
        'page_obj': page_obj,
        'filter_form': filter_form,
        'totals': totals,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
    }
    if request.htmx:
        return render(request, 'admin/trucks/partials/_logistics_table.html', ctx)
    return render(request, 'admin/trucks/logistics_report.html', ctx)


@login_required
def print_logistics_report_view(request):
    """Printer-friendly report."""
    filter_form = LogisticsFilterForm(request.GET)
    today = timezone.now().date()
    start = request.GET.get('start_date') or (today - timedelta(days=30)).strftime('%Y-%m-%d')
    end = request.GET.get('end_date') or today.strftime('%Y-%m-%d')

    try:
        start = datetime.strptime(start, '%Y-%m-%d').date()
        end = datetime.strptime(end, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        start = today - timedelta(days=30)
        end = today

    qs = Trip.objects.select_related(
        'truck', 'destination', 'transporter'
    ).filter(
        Q(actual_departure__isnull=True) |
        Q(actual_departure__date__range=[start, end])
    )

    if filter_form.is_valid():
        cd = filter_form.cleaned_data
        if cd.get('status'):
            qs = qs.filter(status=cd['status'])
        if cd.get('transporter'):
            qs = qs.filter(transporter=cd['transporter'])
        if cd.get('destination'):
            qs = qs.filter(destination=cd['destination'])
        if cd.get('truck'):
            qs = qs.filter(truck=cd['truck'])
        if cd.get('search'):
            sq = cd['search']
            qs = qs.filter(
                Q(truck__truck_number__icontains=sq) |
                Q(transporter__name__icontains=sq) |
                Q(destination__name__icontains=sq) |
                Q(remarks__icontains=sq)
            )

    # ✅ FIXED: Replaced 'fuel_amount' with 'fuel_total_cost'
    totals = qs.aggregate(
        total_transport=Sum('transport_amount'),
        total_fuel=Sum('fuel_total_cost'),  # ← Changed from fuel_amount
        total_tonnage=Sum('weight_tons'),
        count=Count('id')
    )
    for k, v in totals.items():
        if 'total' in k:
            totals[k] = v or Decimal('0.00')
        else:
            totals[k] = v or 0

    ctx = {
        'trips': qs.order_by('actual_departure', 'truck__truck_number'),
        'totals': totals,
        'start_date': start,
        'end_date': end,
        'filter_form': filter_form,
    }
    return render(request, 'admin/trucks/print_logistics_report.html', ctx)


# Improved dashboard_view in views.py
@login_required
def dashboard_view(request):
    """Enhanced Dashboard with comprehensive metrics and proper formatting."""
    today = timezone.now().date()
    this_month_start = today.replace(day=1)
    last_month_start = (this_month_start - timedelta(days=1)).replace(day=1)
    last_month_end = this_month_start - timedelta(days=1)

    # Current month trips (completed only)
    current_trips = Trip.objects.filter(
        actual_departure__date__gte=this_month_start,
        actual_departure__date__lte=today,
        status=Trip.TripStatus.COMPLETED
    )

    # Last month trips (completed only)
    last_trips = Trip.objects.filter(
        actual_departure__date__gte=last_month_start,
        actual_departure__date__lte=last_month_end,
        status=Trip.TripStatus.COMPLETED
    )

    # Current month metrics
    current_metrics = current_trips.aggregate(
        total_revenue=Sum('transport_amount'),
        total_fuel=Sum('fuel_total_cost'),
        total_tonnage=Sum('weight_tons'),
        trip_count=Count('id')
    )

    # Last month metrics
    last_metrics = last_trips.aggregate(
        total_revenue=Sum('transport_amount'),
        total_fuel=Sum('fuel_total_cost'),
        total_tonnage=Sum('weight_tons'),
        trip_count=Count('id')
    )

    # Convert None to 0 and ensure Decimal formatting
    for d in (current_metrics, last_metrics):
        for k, v in d.items():
            if k in ['total_revenue', 'total_fuel']:
                d[k] = v or Decimal('0.00')
            elif k == 'total_tonnage':
                d[k] = v or Decimal('0.00')
            else:
                d[k] = v or 0

    # Calculate percentage changes
    metrics_comparison = {}
    for key in current_metrics:
        cur, prev = current_metrics[key], last_metrics[key]
        if prev and prev > 0:
            if isinstance(prev, Decimal):
                change = ((cur - prev) / prev) * 100
            else:
                change = ((cur - prev) / prev) * 100
            metrics_comparison[key] = {
                'current': cur,
                'previous': prev,
                'change': round(float(change), 1),
                'change_positive': change >= 0
            }
        else:
            metrics_comparison[key] = {
                'current': cur,
                'previous': prev,
                'change': None,
                'change_positive': None
            }

    # Additional analytics
    # Active vs Total entities
    total_trucks = Truck.objects.count()
    active_trucks = Truck.objects.filter(is_active=True).count()
    total_drivers = Driver.objects.count()
    active_drivers = Driver.objects.filter(is_active=True).count()
    total_destinations = Destination.objects.count()
    active_destinations = Destination.objects.filter(is_active=True).count()

    # Trip status breakdown for this month
    trip_status_breakdown = current_trips.values('status').annotate(
        count=Count('id')
    ).order_by('status')

    # Top destinations by tonnage this month
    top_destinations = current_trips.values(
        'destination__name'
    ).annotate(
        total_tonnage=Sum('weight_tons'),
        trip_count=Count('id')
    ).order_by('-total_tonnage')[:5]

    # Top transporters by revenue this month
    top_transporters = current_trips.values(
        'transporter__name'
    ).annotate(
        total_revenue=Sum('transport_amount'),
        trip_count=Count('id')
    ).order_by('-total_revenue')[:5]

    # Outstanding invoices summary
    outstanding_invoices = Invoice.objects.select_related('transporter').filter(
        status__in=[
            Invoice.InvoiceStatus.SENT,
            Invoice.InvoiceStatus.PARTIALLY_PAID,
            Invoice.InvoiceStatus.OVERDUE
        ],
        balance__gt=0
    ).order_by('-due_date')[:10]

    outstanding_summary = outstanding_invoices.aggregate(
        total_outstanding=Sum('balance'),
        count=Count('id')
    )
    outstanding_summary['total_outstanding'] = outstanding_summary['total_outstanding'] or Decimal('0.00')
    outstanding_summary['count'] = outstanding_summary['count'] or 0

    # Recent activity (last 10 trips regardless of status)
    recent_trips = Trip.objects.select_related(
        'truck', 'destination', 'transporter', 'driver'
    ).order_by('-created_at')[:10]

    # Overdue invoices
    overdue_count = Invoice.objects.filter(
        due_date__lt=today,
        balance__gt=0
    ).count()

    ctx = {
        'current_metrics': current_metrics,
        'last_metrics': last_metrics,
        'metrics_comparison': metrics_comparison,
        'recent_trips': recent_trips,
        'outstanding_invoices': outstanding_invoices[:5],  # Limit to 5 for display
        'outstanding_summary': outstanding_summary,
        'overdue_count': overdue_count,

        # Entity counts
        'total_trucks': total_trucks,
        'active_trucks': active_trucks,
        'total_drivers': total_drivers,
        'active_drivers': active_drivers,
        'total_destinations': total_destinations,
        'active_destinations': active_destinations,

        # Analytics
        'trip_status_breakdown': trip_status_breakdown,
        'top_destinations': top_destinations,
        'top_transporters': top_transporters,

        # Date context
        'current_month': this_month_start.strftime('%B %Y'),
        'last_month': last_month_start.strftime('%B %Y'),
        'today': today,
    }
    return render(request, 'admin/trucks/dashboard.html', ctx)


# ------------------------------------------------------------------
# 2.  INVOICE  CRUD
# ------------------------------------------------------------------
@login_required
def invoice_list_view(request):
    today = timezone.now().date()
    start = request.GET.get('start_date') or (today - timedelta(days=90)).strftime('%Y-%m-%d')
    end = request.GET.get('end_date') or today.strftime('%Y-%m-%d')
    status = request.GET.get('status', '')
    transporter = request.GET.get('transporter', '')
    search = request.GET.get('search', '').strip()

    try:
        start = datetime.strptime(start, '%Y-%m-%d').date()
        end = datetime.strptime(end, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        start = today - timedelta(days=90)
        end = today

    qs = Invoice.objects.select_related('transporter').filter(
        invoice_date__range=[start, end]
    )
    if status:
        qs = qs.filter(status=status)
    if transporter:
        qs = qs.filter(transporter_id=transporter)
    if search:
        qs = qs.filter(
            Q(invoice_number__icontains=search) | Q(transporter__name__icontains=search)
        )

    paginator = Paginator(qs.order_by('-invoice_date'), 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    totals = qs.aggregate(
        total_amount=Sum('total_amount'),
        amount_paid=Sum('amount_paid'),
        balance=Sum('balance'),
        count=Count('id'),
    )

    ctx = {
        'page_obj': page_obj,
        'totals': totals,
        'start_date': start.strftime('%Y-%m-%d'),
        'end_date': end.strftime('%Y-%m-%d'),
        'status_filter': status,
        'transporter_filter': transporter,
        'search_query': search,
        'transporters': Transporter.objects.filter(is_active=True).order_by('name'),
        'status_choices': Invoice.InvoiceStatus.choices,
    }
    if request.htmx:
        return render(request, 'admin/trucks/partials/_invoice_list.html', ctx)
    return render(request, 'admin/trucks/invoice_list.html', ctx)


@login_required
def invoice_create_view(request):
    if request.method == 'POST':
        form = InvoiceForm(request.POST)
        if form.is_valid():
            inv = form.save()
            messages.success(request, f"Invoice {inv.invoice_number} created.")
            if request.htmx:
                return HttpResponse(status=204, headers={'HX-Trigger': 'invoiceCreated'})
            return redirect('trucks:invoice_detail', pk=inv.pk)
    else:
        form = InvoiceForm()
    ctx = {'form': form, 'title': 'Create New Invoice', 'action': 'create'}
    if request.htmx:
        return render(request, 'admin/trucks/partials/_invoice_form.html', ctx)
    return render(request, 'admin/trucks/invoice_form.html', ctx)


@login_required
def invoice_create_from_trips_view(request):
    transporter_id = request.GET.get('transporter')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    status = request.GET.get('status')
    truck_id = request.GET.get('truck')
    destination_id = request.GET.get('destination')
    search = request.GET.get('search')

    if not transporter_id or not start_date or not end_date:
        messages.error(request, "Missing required parameters.")
        return redirect('trucks:logistics_report')

    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        transporter = Transporter.objects.get(pk=transporter_id)
    except (ValueError, Transporter.DoesNotExist):
        messages.error(request, "Invalid parameters.")
        return redirect('trucks:logistics_report')

    # ✅ Auto-generate unique invoice number
    transporter_initials = "".join([word[0].upper() for word in transporter.name.split()[:3]])
    invoice_number = f"INV-{start_date.strftime('%Y%m%d')}-{transporter_initials}"

    # ✅ Use get_or_create with invoice_number in defaults
    invoice, created = Invoice.objects.get_or_create(
        transporter=transporter,
        period_start=start_date,
        period_end=end_date,
        defaults={
            'invoice_number': invoice_number,
            'invoice_date': timezone.now().date(),
            'status': Invoice.InvoiceStatus.DRAFT,
        }
    )

    if not created:
        messages.info(request, f"Updated existing invoice {invoice.invoice_number}.")
    else:
        messages.success(request, f"Created new invoice {invoice.invoice_number}.")

    # ✅ Build filter query
    trips = Trip.objects.filter(
        transporter=transporter,
    ).filter(
        Q(actual_departure__isnull=True) |
        Q(actual_departure__date__range=[start_date, end_date])
    )

    # ✅ Apply additional filters
    if status:
        trips = trips.filter(status=status)
    if truck_id:
        trips = trips.filter(truck_id=truck_id)
    if destination_id:
        trips = trips.filter(destination_id=destination_id)
    if search:
        trips = trips.filter(
            Q(trip_number__icontains=search) |
            Q(truck__truck_number__icontains=search) |
            Q(destination__name__icontains=search) |
            Q(transporter__name__icontains=search) |
            Q(remarks__icontains=search)
        )

    print(f"Found {trips.count()} trips for {transporter.name} between {start_date} and {end_date}")  # 👈 Debug

    for trip in trips:
        trip.invoice = invoice
        trip.save()
        print(f"Linked trip {trip.trip_number} to invoice {invoice.invoice_number}")  # 👈 Debug

    # ✅ Recalculate totals
    invoice.calculate_totals()
    invoice.save()

    return redirect('trucks:invoice_detail', pk=invoice.pk)

@login_required
def invoice_detail_view(request, pk):
    inv = get_object_or_404(
        Invoice.objects.select_related('transporter').prefetch_related(
            'trips__truck', 'trips__destination', 'credits', 'payments'
        ), pk=pk
    )
    return render(request, 'admin/trucks/invoice_detail.html', {'invoice': inv})


# ------------------------------------------------------------------
# 3.  TRIP  CRUD  (operational)
# ------------------------------------------------------------------
@login_required
def trip_list_view(request):
    today = timezone.now().date()
    start = request.GET.get('start_date')
    end = request.GET.get('end_date')
    status = request.GET.get('status', '')
    truck = request.GET.get('truck', '')
    transporter = request.GET.get('transporter', '')  # ✅ Added transporter filter
    search = request.GET.get('search', '').strip()

    # Only parse dates if provided
    if start:
        try:
            start = datetime.strptime(start, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            start = None
    if end:
        try:
            end = datetime.strptime(end, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            end = None

    # Start with ALL trips
    qs = Trip.objects.select_related(
        'truck', 'driver', 'origin', 'destination', 'transporter'
    )

    # Apply date filter ONLY if both start and end are provided
    if start and end:
        qs = qs.filter(
            Q(planned_departure__isnull=True) |
            Q(planned_departure__date__range=[start, end])
        )

    # Apply filters
    if status:
        qs = qs.filter(status=status)
    if truck:
        qs = qs.filter(truck_id=truck)
    if transporter:  # ✅ Apply transporter filter
        qs = qs.filter(transporter_id=transporter)
    if search:
        qs = qs.filter(
            Q(trip_number__icontains=search) |
            Q(truck__truck_number__icontains=search) |
            Q(destination__name__icontains=search) |
            Q(transporter__name__icontains=search)
        )

    paginator = Paginator(qs.order_by('-planned_departure'), 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    # ✅ Pass active transporters to context for filter dropdown
    ctx = {
        'page_obj': page_obj,
        'start_date': start.strftime('%Y-%m-%d') if start else (today - timedelta(days=30)).strftime('%Y-%m-%d'),
        'end_date': end.strftime('%Y-%m-%d') if end else today.strftime('%Y-%m-%d'),
        'status_filter': status,
        'truck_filter': truck,
        'transporter_filter': transporter,  # ✅ Pass transporter filter value
        'search_query': search,
        'trucks': Truck.objects.filter(is_active=True).order_by('truck_number'),
        'transporters': Transporter.objects.filter(is_active=True).order_by('name'),  # ✅ Active transporters
        'status_choices': Trip.TripStatus.choices,
    }
    if request.htmx:
        return render(request, 'admin/trucks/partials/_trip_list.html', ctx)
    return render(request, 'admin/trucks/trip_list.html', ctx)


@login_required
def trip_create_view(request):
    if request.method == 'POST':
        form = TripForm(request.POST)
        if form.is_valid():
            trip = form.save()
            messages.success(request, f"Trip {trip.trip_number} created.")
            if request.htmx:
                return HttpResponse(status=204, headers={'HX-Trigger': 'tripCreated'})
            return redirect('trucks:trip_list')
    else:
        form = TripForm()
    ctx = {'form': form, 'title': 'Create New Trip', 'action': 'create'}
    if request.htmx:
        return render(request, 'admin/trucks/partials/_trip_form.html', ctx)
    return render(request, 'admin/trucks/trip_form.html', ctx)


@login_required
def trip_edit_view(request, pk):
    trip = get_object_or_404(Trip, pk=pk)
    if request.method == 'POST':
        form = TripForm(request.POST, instance=trip)
        if form.is_valid():
            trip = form.save()
            messages.success(request, f"Trip {trip.trip_number} updated.")
            if request.htmx:
                return HttpResponse(status=204, headers={'HX-Trigger': 'tripUpdated'})
            return redirect('trucks:trip_list')
        else:
            # Debug: Print form errors
            print("Form errors:", form.errors)  # 👈 Add this
            messages.error(request, "Please correct the errors below.")
    else:
        form = TripForm(instance=trip)
    ctx = {'form': form, 'object': trip, 'title': f"Edit Trip – {trip}", 'action': 'edit'}
    if request.htmx:
        return render(request, 'admin/trucks/partials/_trip_form.html', ctx)
    return render(request, 'admin/trucks/trip_form.html', ctx)


@login_required
def trip_detail_view(request, pk):
    trip = get_object_or_404(Trip, pk=pk)
    return render(request, 'admin/trucks/trip_detail.html', {'object': trip})


@login_required
def payment_create_view(request, invoice_id):
    invoice = get_object_or_404(Invoice, pk=invoice_id)

    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.invoice = invoice  # Set the invoice relationship here
            payment.save()

            # Recalculate invoice totals after payment
            invoice.calculate_totals()
            invoice.save()

            messages.success(request, f"Payment of {payment.amount} recorded for invoice {invoice.invoice_number}")
            return redirect('trucks:invoice_detail', pk=invoice.pk)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = PaymentForm()

    ctx = {
        'form': form,
        'invoice': invoice,
        'title': f'Record Payment for {invoice.invoice_number}',
        'submit_text': 'Record Payment'
    }

    return render(request, 'admin/trucks/payment_form.html', ctx)


@login_required
def invoice_credit_create_view(request, invoice_id):
    invoice = get_object_or_404(Invoice, pk=invoice_id)

    if request.method == 'POST':
        form = InvoiceCreditForm(request.POST, invoice=invoice)
        if form.is_valid():
            credit = form.save(commit=False)
            credit.invoice = invoice  # Set the invoice relationship here
            credit.save()

            # Recalculate invoice totals after adding credit
            invoice.calculate_totals()
            invoice.save()

            messages.success(request, f"Credit of {credit.amount} applied to invoice {invoice.invoice_number}")
            return redirect('trucks:invoice_detail', pk=invoice.pk)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = InvoiceCreditForm(invoice=invoice)

    ctx = {
        'form': form,
        'invoice': invoice,
        'title': f'Apply Credit to {invoice.invoice_number}',
        'submit_text': 'Apply Credit'
    }
    return render(request, 'admin/trucks/invoice_credit_form.html', ctx)
# ------------------------------------------------------------------
# 4.  FUEL  &  EXPENSE  CRUD
# ------------------------------------------------------------------
@login_required
def expense_list_view(request):
    today = timezone.now().date()
    start = request.GET.get('start_date') or (today - timedelta(days=30)).strftime('%Y-%m-%d')
    end = request.GET.get('end_date') or today.strftime('%Y-%m-%d')
    level = request.GET.get('expense_level', '')
    category = request.GET.get('category', '')

    try:
        start = datetime.strptime(start, '%Y-%m-%d').date()
        end = datetime.strptime(end, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        start = today - timedelta(days=30)
        end = today

    qs = Expense.objects.select_related(
        'category', 'trip__truck', 'truck'
    ).filter(date__range=[start, end])
    if level:
        qs = qs.filter(expense_level=level)
    if category:
        qs = qs.filter(category_id=category)

    paginator = Paginator(qs.order_by('-date'), 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    totals = qs.aggregate(total_amount=Sum('amount'), count=Count('id'))

    ctx = {
        'page_obj': page_obj,
        'totals': totals,
        'start_date': start.strftime('%Y-%m-%d'),
        'end_date': end.strftime('%Y-%m-%d'),
        'level_filter': level,
        'category_filter': category,
        'categories': ExpenseCategory.objects.filter(is_active=True).order_by('name'),
        'level_choices': Expense.ExpenseLevel.choices,
    }
    return render(request, 'admin/trucks/expense_list.html', ctx)


@login_required
def expense_create_view(request):
    if request.method == 'POST':
        form = ExpenseForm(request.POST)
        if form.is_valid():
            exp = form.save()
            messages.success(request, f"Expense {exp.description} created.")
            return redirect('trucks:expense_list')
    else:
        form = ExpenseForm()
    return render(request, 'admin/trucks/expense_form.html', {'form': form, 'title': 'Create New Expense'})


# ------------------------------------------------------------------
# 5.  REUSABLE  CRUD  CLASS  (master tables) — FIXED
# ------------------------------------------------------------------
class ModelCRUD:
    """
    One class to rule them all — updated to use is_active, not is_removed
    """

    cfg = {
        "driver": {
            "model": Driver,
            "form": DriverForm,
            "base": "driver",
            "redirect": "trucks:driver_list",  # ✅ Namespaced
            "trigger": "driver",
        },
        "truck": {
            "model": Truck,
            "form": TruckForm,
            "base": "truck",
            "redirect": "trucks:truck_list",  # ✅ Namespaced
            "trigger": "truck",
        },
        "destination": {
            "model": Destination,
            "form": DestinationForm,
            "base": "destination",
            "redirect": "trucks:destination_list",  # ✅ Namespaced
            "trigger": "destination",
        },
        "transporter": {
            "model": Transporter,
            "form": TransporterForm,
            "base": "transporter",
            "redirect": "trucks:transporter_list",  # ✅ Namespaced
            "trigger": "transporter",
        },
        "expensecategory": {
            "model": ExpenseCategory,
            "form": ExpenseCategoryForm,
            "base": "expense_category",
            "redirect": "trucks:expense_category_list",  # ✅ Namespaced
            "trigger": "category",
        },
        "cargotype": {
            "model": CargoType,
            "form": CargoTypeForm,
            "base": "cargo_type",
            "redirect": "trucks:cargo_type_list",  # ✅ Namespaced
            "trigger": "cargoType",
        },
    }

    @classmethod
    def list(cls, request, kind):
        c = cls.cfg[kind]
        model, base, trigger = c["model"], c["base"], c["trigger"]
        qs = model.objects.all()
        search = request.GET.get("search", "").strip()
        status = request.GET.get("status", "")
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))
        if status == "active":
            qs = qs.filter(is_active=True)
        elif status == "inactive":
            qs = qs.filter(is_active=False)

        paginator = Paginator(qs, 25)
        page_obj = paginator.get_page(request.GET.get("page"))

        ctx = {
            "page_obj": page_obj,
            "search_query": search,
            "status_filter": status,
            f"total_{kind}s": qs.count(),
            f"active_{kind}s": qs.filter(is_active=True).count(),
        }
        if request.htmx:
            return render(request, f"admin/trucks/partials/_{base}_list.html", ctx)
        return render(request, f"admin/trucks/{base}_list.html", ctx)

    @classmethod
    def create(cls, request, kind):
        c = cls.cfg[kind]
        model, form_cls, base, redirect_url, trigger = (
            c["model"], c["form"], c["base"], c["redirect"], c["trigger"]
        )
        if request.method == "POST":
            form = form_cls(request.POST, request.FILES)
            if form.is_valid():
                obj = form.save()
                messages.success(request, f"{model._meta.verbose_name} {obj} created.")
                if request.htmx:
                    return HttpResponse(status=204, headers={"HX-Trigger": f"{trigger}Created"})
                return redirect(redirect_url)  # ✅ Now uses namespaced URL
        else:
            form = form_cls()

        ctx = {"form": form, "title": f"Add New {model._meta.verbose_name}", "action": "create"}
        if request.htmx:
            return render(request, f"admin/trucks/partials/_{base}_form.html", ctx)
        return render(request, f"admin/trucks/{base}_form.html", ctx)

    @classmethod
    def edit(cls, request, kind, pk):
        c = cls.cfg[kind]
        model, form_cls, base, redirect_url, trigger = (
            c["model"], c["form"], c["base"], c["redirect"], c["trigger"]
        )
        obj = get_object_or_404(model, pk=pk)
        if request.method == "POST":
            form = form_cls(request.POST, request.FILES, instance=obj)
            if form.is_valid():
                obj = form.save()
                messages.success(request, f"{model._meta.verbose_name} {obj} updated.")
                if request.htmx:
                    return HttpResponse(status=204, headers={"HX-Trigger": f"{trigger}Updated"})
                return redirect(redirect_url)  # ✅ Now uses namespaced URL
        else:
            form = form_cls(instance=obj)

        ctx = {
            "form": form,
            "object": obj,
            "title": f"Edit {model._meta.verbose_name} – {obj}",
            "action": "edit",
        }
        if request.htmx:
            return render(request, f"admin/trucks/partials/_{base}_form.html", ctx)
        return render(request, f"admin/trucks/{base}_form.html", ctx)

    @classmethod
    def delete(cls, request, kind, pk):
        c = cls.cfg[kind]
        model, base, redirect_url, trigger = (
            c["model"], c["base"], c["redirect"], c["trigger"]
        )
        obj = get_object_or_404(model, pk=pk)
        if request.method == "POST":
            obj.is_active = False
            obj.save()
            messages.success(request, f"{model._meta.verbose_name} {obj} deactivated.")
            if request.htmx:
                return HttpResponse(status=204, headers={"HX-Trigger": f"{trigger}Deleted"})
            return redirect(redirect_url)  # ✅ Now uses namespaced URL

        ctx = {"object": obj}
        if request.htmx:
            return render(request, f"admin/trucks/partials/_{base}_confirm_delete.html", ctx)
        return render(request, f"admin/trucks/{base}_confirm_delete.html", ctx)

    @classmethod
    def detail(cls, request, kind, pk):
        c = cls.cfg[kind]
        model, base = c["model"], c["base"]
        obj = get_object_or_404(model, pk=pk)
        ctx = {"object": obj, "title": f"{model._meta.verbose_name} – {obj}"}
        if request.htmx:
            return render(request, f"admin/trucks/partials/_{base}_detail.html", ctx)
        return render(request, f"admin/trucks/{base}_detail.html", ctx)


# ------------------------------------------------------------------
# 6.  TINY  WRAPPERS  so urls.py stays identical — UPDATED TO NAMESPACE
# ------------------------------------------------------------------
driver_list_view       = login_required(lambda r: ModelCRUD.list(r, "driver"))
driver_create_view     = login_required(lambda r: ModelCRUD.create(r, "driver"))
driver_detail_view     = login_required(lambda r, pk: ModelCRUD.detail(r, "driver", pk))
driver_edit_view       = login_required(lambda r, pk: ModelCRUD.edit(r, "driver", pk))
driver_delete_view     = login_required(lambda r, pk: ModelCRUD.delete(r, "driver", pk))

truck_list_view        = login_required(lambda r: ModelCRUD.list(r, "truck"))
truck_create_view      = login_required(lambda r: ModelCRUD.create(r, "truck"))
truck_detail_view      = login_required(lambda r, pk: ModelCRUD.detail(r, "truck", pk))
truck_edit_view        = login_required(lambda r, pk: ModelCRUD.edit(r, "truck", pk))
truck_delete_view      = login_required(lambda r, pk: ModelCRUD.delete(r, "truck", pk))

destination_list_view      = login_required(lambda r: ModelCRUD.list(r, "destination"))
destination_create_view    = login_required(lambda r: ModelCRUD.create(r, "destination"))
destination_edit_view      = login_required(lambda r, pk: ModelCRUD.edit(r, "destination", pk))
destination_delete_view    = login_required(lambda r, pk: ModelCRUD.delete(r, "destination", pk))

transporter_list_view      = login_required(lambda r: ModelCRUD.list(r, "transporter"))
transporter_create_view    = login_required(lambda r: ModelCRUD.create(r, "transporter"))
transporter_edit_view      = login_required(lambda r, pk: ModelCRUD.edit(r, "transporter", pk))
transporter_delete_view    = login_required(lambda r, pk: ModelCRUD.delete(r, "transporter", pk))

expense_category_list_view   = login_required(lambda r: ModelCRUD.list(r, "expensecategory"))
expense_category_create_view = login_required(lambda r: ModelCRUD.create(r, "expensecategory"))
expense_category_edit_view   = login_required(lambda r, pk: ModelCRUD.edit(r, "expensecategory", pk))
expense_category_delete_view = login_required(lambda r, pk: ModelCRUD.delete(r, "expensecategory", pk))

cargo_type_list_view   = login_required(lambda r: ModelCRUD.list(r, "cargotype"))
cargo_type_create_view = login_required(lambda r: ModelCRUD.create(r, "cargotype"))
cargo_type_edit_view   = login_required(lambda r, pk: ModelCRUD.edit(r, "cargotype", pk))
cargo_type_delete_view = login_required(lambda r, pk: ModelCRUD.delete(r, "cargotype", pk))


# ------------------------------------------------------------------
# 7.  API  END-POINTS  — FIXED
# ------------------------------------------------------------------
@login_required
def api_truck_info(request, truck_id):
    try:
        t = Truck.objects.get(id=truck_id, is_active=True)
        return JsonResponse({
            'truck_number': t.truck_number,
            'make': t.make or '',
            'model': t.model or '',
            'capacity_tons': str(t.capacity_tons) if t.capacity_tons else '',
            'fuel_tank_capacity': str(t.fuel_tank_capacity) if t.fuel_tank_capacity else '',
        })
    except Truck.DoesNotExist:
        return JsonResponse({'error': 'Truck not found'}, status=404)


@login_required
def api_destination_info(request, destination_id):
    try:
        d = Destination.objects.get(id=destination_id, is_active=True)
        return JsonResponse({'name': d.name, 'region': d.region or '', 'country': d.country})
    except Destination.DoesNotExist:
        return JsonResponse({'error': 'Destination not found'}, status=404)


@login_required
def api_transporter_invoices(request, transporter_id):
    invoices = Invoice.objects.filter(
        transporter_id=transporter_id,
        status__in=[Invoice.InvoiceStatus.DRAFT, Invoice.InvoiceStatus.SENT]
    ).values('id', 'invoice_number', 'period_start', 'period_end')
    return JsonResponse({'invoices': list(invoices)})


@require_http_methods(["POST"])
@login_required
def api_calculate_transport_amount(request):
    try:
        tonnage = Decimal(request.POST.get('tonnage', '0'))
        rate_per_ton = Decimal(request.POST.get('rate_per_ton', '0'))
        return JsonResponse({'total_transport_amount': str(tonnage * rate_per_ton)})
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid input'}, status=400)


@require_http_methods(["POST"])
@login_required
def api_calculate_fuel_amount(request):
    try:
        litres = Decimal(request.POST.get('litres_of_fuel', '0'))
        cost_per_litre = Decimal(request.POST.get('cost_per_litre', '0'))
        return JsonResponse({'fuel_amount': str(litres * cost_per_litre)})
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid input'}, status=400)


@login_required
def api_invoice_summary(request, invoice_id):
    try:
        inv = Invoice.objects.get(id=invoice_id)
        inv.calculate_totals()
        return JsonResponse({
            'total_transport_amount': str(inv.total_transport_amount),
            'total_fuel_amount': str(inv.total_fuel_amount),
            'total_credits': str(inv.total_credits),
            'total_amount': str(inv.total_amount),
            'amount_paid': str(inv.amount_paid),
            'balance': str(inv.balance),
            'trip_count': inv.trips.count(),
        })
    except Invoice.DoesNotExist:
        return JsonResponse({'error': 'Invoice not found'}, status=404)


@login_required
def analytics_dashboard_view(request):
    """Main analytics dashboard with date filtering"""
    today = timezone.now().date()
    default_start = today - timedelta(days=30)

    # Get date parameters
    start_date = request.GET.get('start_date') or default_start.strftime('%Y-%m-%d')
    end_date = request.GET.get('end_date') or today.strftime('%Y-%m-%d')

    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        start_date = default_start
        end_date = today

    # Base queryset for completed trips in date range
    base_trips = Trip.objects.filter(
        status=Trip.TripStatus.COMPLETED,
        actual_departure__date__range=[start_date, end_date]
    ).select_related('truck', 'transporter', 'destination')

    # Overall business metrics
    business_metrics = get_business_metrics(start_date, end_date)

    # Top performers
    top_trucks = get_top_trucks_by_profit(start_date, end_date)
    top_transporters = get_top_transporters_by_revenue(start_date, end_date)
    top_destinations = get_top_destinations_by_volume(start_date, end_date)

    # Profit trends (weekly breakdown)
    profit_trends = get_profit_trends(start_date, end_date)

    context = {
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'business_metrics': business_metrics,
        'top_trucks': top_trucks,
        'top_transporters': top_transporters,
        'top_destinations': top_destinations,
        'profit_trends': profit_trends,
        'date_range_days': (end_date - start_date).days + 1,
    }

    if request.htmx:
        return render(request, 'admin/trucks/partials/_analytics_content.html', context)
    return render(request, 'admin/trucks/analytics_dashboard.html', context)


def get_business_metrics(start_date, end_date):
    """Calculate overall business metrics for the period with proper expense allocation"""

    # Revenue from completed trips
    trip_metrics = Trip.objects.filter(
        status=Trip.TripStatus.COMPLETED,
        actual_departure__date__range=[start_date, end_date]
    ).aggregate(
        total_revenue=Sum('transport_amount'),
        total_fuel_cost=Sum('fuel_total_cost'),
        total_tonnage=Sum('weight_tons'),
        trip_count=Count('id')
    )

    # Get all expense types for the period
    expenses_breakdown = get_expenses_for_period(start_date, end_date)

    # Calculate totals
    total_revenue = trip_metrics['total_revenue'] or Decimal('0.00')
    total_fuel_cost = trip_metrics['total_fuel_cost'] or Decimal('0.00')

    # Total expenses = fuel + all other expenses
    total_expenses = (
            total_fuel_cost +
            expenses_breakdown['business_expenses'] +
            expenses_breakdown['truck_expenses'] +
            expenses_breakdown['trip_expenses']
    )

    gross_profit = total_revenue - total_fuel_cost
    net_profit = total_revenue - total_expenses

    # Profit margins
    gross_margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else Decimal('0.00')
    net_margin = (net_profit / total_revenue * 100) if total_revenue > 0 else Decimal('0.00')

    # Revenue per ton
    revenue_per_ton = (total_revenue / trip_metrics['total_tonnage']) if trip_metrics['total_tonnage'] and trip_metrics[
        'total_tonnage'] > 0 else Decimal('0.00')

    return {
        'total_revenue': total_revenue,
        'total_expenses': total_expenses,
        'total_fuel_cost': total_fuel_cost,
        'business_expenses': expenses_breakdown['business_expenses'],
        'truck_expenses': expenses_breakdown['truck_expenses'],
        'trip_expenses': expenses_breakdown['trip_expenses'],
        'gross_profit': gross_profit,
        'net_profit': net_profit,
        'gross_margin': gross_margin,
        'net_margin': net_margin,
        'total_tonnage': trip_metrics['total_tonnage'] or Decimal('0.00'),
        'trip_count': trip_metrics['trip_count'] or 0,
        'revenue_per_ton': revenue_per_ton,
        'expense_breakdown': expenses_breakdown,
    }


def get_expenses_for_period(start_date, end_date, truck_id=None, trip_ids=None):
    """
    Get expenses broken down by level for a specific period
    Optionally filter for specific truck or trips
    """
    base_filter = {'date__range': [start_date, end_date]}

    # Business-level expenses (always included for any period)
    business_expenses = Expense.objects.filter(
        expense_level=Expense.ExpenseLevel.BUSINESS,
        **base_filter
    ).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')

    # Truck-level expenses
    truck_filter = dict(base_filter)
    truck_filter['expense_level'] = Expense.ExpenseLevel.TRUCK
    if truck_id:
        truck_filter['truck_id'] = truck_id

    truck_expenses = Expense.objects.filter(**truck_filter).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')

    # Trip-level expenses (only for completed trips)
    trip_filter = dict(base_filter)
    trip_filter.update({
        'expense_level': Expense.ExpenseLevel.TRIP,
        'trip__status': Trip.TripStatus.COMPLETED
    })
    if trip_ids:
        trip_filter['trip_id__in'] = trip_ids
    elif truck_id:
        trip_filter['trip__truck_id'] = truck_id

    trip_expenses = Expense.objects.filter(**trip_filter).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')

    return {
        'business_expenses': business_expenses,
        'truck_expenses': truck_expenses,
        'trip_expenses': trip_expenses,
        'total_non_fuel_expenses': business_expenses + truck_expenses + trip_expenses
    }


def get_top_trucks_by_profit(start_date, end_date, limit=10):
    """Get trucks ranked by profitability with proper expense allocation"""

    truck_performance = Trip.objects.filter(
        status=Trip.TripStatus.COMPLETED,
        actual_departure__date__range=[start_date, end_date]
    ).values(
        'truck__id', 'truck__truck_number', 'truck__make', 'truck__model'
    ).annotate(
        total_revenue=Sum('transport_amount'),
        total_fuel_cost=Sum('fuel_total_cost'),
        total_tonnage=Sum('weight_tons'),
        trip_count=Count('id'),
        gross_profit=Sum('transport_amount') - Sum('fuel_total_cost')
    ).order_by('-gross_profit')[:limit]

    # Add detailed expense breakdown for each truck
    for truck_data in truck_performance:
        truck_id = truck_data['truck__id']

        # Get completed trip IDs for this truck in the period
        completed_trip_ids = list(Trip.objects.filter(
            truck_id=truck_id,
            status=Trip.TripStatus.COMPLETED,
            actual_departure__date__range=[start_date, end_date]
        ).values_list('id', flat=True))

        # Get expenses for this truck
        expenses = get_expenses_for_period(
            start_date, end_date,
            truck_id=truck_id,
            trip_ids=completed_trip_ids
        )

        # Calculate profitability
        total_revenue = truck_data['total_revenue'] or Decimal('0.00')
        total_fuel_cost = truck_data['total_fuel_cost'] or Decimal('0.00')
        total_other_expenses = expenses['total_non_fuel_expenses']
        total_expenses = total_fuel_cost + total_other_expenses
        net_profit = total_revenue - total_expenses

        # Update truck data
        truck_data.update({
            'truck_expenses': expenses['truck_expenses'],
            'trip_expenses': expenses['trip_expenses'],
            'total_other_expenses': total_other_expenses,
            'total_expenses': total_expenses,
            'net_profit': net_profit,
            'profit_margin': (net_profit / total_revenue * 100) if total_revenue > 0 else Decimal('0.00'),
            'revenue_per_trip': (total_revenue / truck_data['trip_count']) if truck_data['trip_count'] > 0 else Decimal(
                '0.00'),
            'expense_breakdown': expenses
        })

    # Re-sort by net profit
    truck_performance = sorted(truck_performance, key=lambda x: x['net_profit'], reverse=True)

    return truck_performance


def get_top_transporters_by_revenue(start_date, end_date, limit=10):
    """Get transporters ranked by revenue"""
    return Trip.objects.filter(
        status=Trip.TripStatus.COMPLETED,
        actual_departure__date__range=[start_date, end_date]
    ).values(
        'transporter__id', 'transporter__name'
    ).annotate(
        total_revenue=Sum('transport_amount'),
        total_tonnage=Sum('weight_tons'),
        trip_count=Count('id'),
        avg_rate_per_ton=Avg('rate_per_ton')
    ).order_by('-total_revenue')[:limit]


def get_top_destinations_by_volume(start_date, end_date, limit=10):
    """Get destinations ranked by tonnage volume"""
    return Trip.objects.filter(
        status=Trip.TripStatus.COMPLETED,
        actual_departure__date__range=[start_date, end_date]
    ).values(
        'destination__id', 'destination__name', 'destination__region'
    ).annotate(
        total_tonnage=Sum('weight_tons'),
        total_revenue=Sum('transport_amount'),
        trip_count=Count('id'),
        avg_tonnage_per_trip=Avg('weight_tons')
    ).order_by('-total_tonnage')[:limit]


def get_profit_trends(start_date, end_date):
    """Get weekly profit trends with proper expense allocation"""
    from django.db.models import DateField
    from django.db.models.functions import TruncWeek

    weekly_data = Trip.objects.filter(
        status=Trip.TripStatus.COMPLETED,
        actual_departure__date__range=[start_date, end_date]
    ).annotate(
        week=TruncWeek('actual_departure', output_field=DateField())
    ).values('week').annotate(
        revenue=Sum('transport_amount'),
        fuel_cost=Sum('fuel_total_cost'),
        trip_count=Count('id')
    ).order_by('week')

    # Add expenses by week with proper allocation
    for week_data in weekly_data:
        week_start = week_data['week']
        week_end = week_start + timedelta(days=6)

        # Get all expenses for this week
        week_expenses = get_expenses_for_period(week_start, week_end)

        revenue = week_data['revenue'] or Decimal('0.00')
        fuel_cost = week_data['fuel_cost'] or Decimal('0.00')
        total_other_expenses = week_expenses['total_non_fuel_expenses']
        total_expenses = fuel_cost + total_other_expenses

        week_data.update({
            'business_expenses': week_expenses['business_expenses'],
            'truck_expenses': week_expenses['truck_expenses'],
            'trip_expenses': week_expenses['trip_expenses'],
            'total_other_expenses': total_other_expenses,
            'total_expenses': total_expenses,
            'gross_profit': revenue - fuel_cost,
            'net_profit': revenue - total_expenses,
            'expense_breakdown': week_expenses
        })

    return weekly_data


@login_required
def truck_comparison_view(request):
    """Compare multiple trucks side by side with proper HTMX handling"""
    today = timezone.now().date()
    default_start = today - timedelta(days=30)

    # Get parameters - handle both GET and POST for HTMX compatibility
    start_date = request.GET.get('start_date') or request.POST.get('start_date') or default_start.strftime('%Y-%m-%d')
    end_date = request.GET.get('end_date') or request.POST.get('end_date') or today.strftime('%Y-%m-%d')
    truck_ids = request.GET.getlist('trucks') or request.POST.getlist('trucks')

    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        start_date = default_start
        end_date = today

    trucks_data = []
    if truck_ids:
        for truck_id in truck_ids:
            try:
                truck = Truck.objects.get(id=truck_id, is_active=True)
                truck_metrics = get_truck_detailed_metrics(truck, start_date, end_date)
                trucks_data.append(truck_metrics)
            except Truck.DoesNotExist:
                continue

    # Get all active trucks for the selector
    all_trucks = Truck.objects.filter(is_active=True).select_related('current_driver').order_by('truck_number')

    context = {
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'trucks_data': trucks_data,
        'selected_trucks': [str(tid) for tid in truck_ids],
        'all_trucks': all_trucks,
        'date_range_days': (end_date - start_date).days + 1,
    }

    # HTMX partial update
    if request.headers.get('HX-Request'):
        return render(request, 'admin/trucks/partials/_truck_comparison.html', context)

    # Full page load
    return render(request, 'admin/trucks/truck_comparison.html', context)


def get_truck_detailed_metrics(truck, start_date, end_date):
    """Get detailed metrics for a specific truck with proper expense handling"""
    # Trip metrics for this truck
    trip_metrics = Trip.objects.filter(
        truck=truck,
        status=Trip.TripStatus.COMPLETED,
        actual_departure__date__range=[start_date, end_date]
    ).aggregate(
        total_revenue=Sum('transport_amount'),
        total_fuel_cost=Sum('fuel_total_cost'),
        total_tonnage=Sum('weight_tons'),
        trip_count=Count('id'),
        avg_tonnage=Avg('weight_tons')
    )

    # Get completed trip IDs for expense calculation
    completed_trip_ids = list(Trip.objects.filter(
        truck=truck,
        status=Trip.TripStatus.COMPLETED,
        actual_departure__date__range=[start_date, end_date]
    ).values_list('id', flat=True))

    # Get all expenses related to this truck
    expenses = get_expenses_for_period(
        start_date, end_date,
        truck_id=truck.id,
        trip_ids=completed_trip_ids
    )

    # Get expense categories for this truck (TRUCK + TRIP level only)
    expense_categories = Expense.objects.filter(
        Q(expense_level=Expense.ExpenseLevel.TRUCK, truck=truck) |
        Q(expense_level=Expense.ExpenseLevel.TRIP, trip__truck=truck, trip__status=Trip.TripStatus.COMPLETED),
        date__range=[start_date, end_date]
    ).values('category__name').annotate(
        total_amount=Sum('amount')
    ).order_by('-total_amount')

    # Calculate metrics
    total_revenue = trip_metrics['total_revenue'] or Decimal('0.00')
    total_fuel_cost = trip_metrics['total_fuel_cost'] or Decimal('0.00')
    total_other_expenses = expenses['total_non_fuel_expenses']
    total_expenses = total_fuel_cost + total_other_expenses
    total_tonnage = trip_metrics['total_tonnage'] or Decimal('0.00')
    net_profit = total_revenue - total_expenses
    gross_profit = total_revenue - total_fuel_cost
    profit_margin = (net_profit / total_revenue * 100) if total_revenue > 0 else Decimal('0.00')
    gross_margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else Decimal('0.00')
    revenue_per_trip = (total_revenue / trip_metrics['trip_count']) if trip_metrics['trip_count'] > 0 else Decimal('0.00')
    fuel_efficiency = (total_fuel_cost / total_tonnage) if total_tonnage > 0 else Decimal('0.00')
    cost_per_ton = (total_expenses / total_tonnage) if total_tonnage > 0 else Decimal('0.00')

    return {
        'truck': truck,
        'total_revenue': total_revenue,
        'total_fuel_cost': total_fuel_cost,
        'business_expenses': expenses['business_expenses'],
        'truck_expenses': expenses['truck_expenses'],      # ← Total amount (Decimal)
        'trip_expenses': expenses['trip_expenses'],        # ← Total amount (Decimal)
        'total_other_expenses': total_other_expenses,
        'total_expenses': total_expenses,
        'gross_profit': gross_profit,
        'net_profit': net_profit,
        'gross_margin': gross_margin,
        'profit_margin': profit_margin,
        'trip_count': trip_metrics['trip_count'] or 0,
        'total_tonnage': total_tonnage,
        'avg_tonnage': trip_metrics['avg_tonnage'] or Decimal('0.00'),
        'revenue_per_trip': revenue_per_trip,
        'fuel_efficiency': fuel_efficiency,
        'cost_per_ton': cost_per_ton,
        'expense_categories': expense_categories,          # ← ✅ NEW: List of {category__name, total_amount}
        'expense_breakdown': expenses,
    }


@login_required
def trip_profitability_view(request):
    """Detailed trip-by-trip profitability analysis"""
    today = timezone.now().date()
    start_date = request.GET.get('start_date') or (today - timedelta(days=30)).strftime('%Y-%m-%d')
    end_date = request.GET.get('end_date') or today.strftime('%Y-%m-%d')
    truck_filter = request.GET.get('truck', '')
    transporter_filter = request.GET.get('transporter', '')

    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        start_date = today - timedelta(days=30)
        end_date = today

    # Base queryset
    trips = Trip.objects.filter(
        status=Trip.TripStatus.COMPLETED,
        actual_departure__date__range=[start_date, end_date]
    ).select_related('truck', 'transporter', 'destination')

    if truck_filter:
        trips = trips.filter(truck_id=truck_filter)
    if transporter_filter:
        trips = trips.filter(transporter_id=transporter_filter)

    # Calculate profitability for each trip
    trips_with_profit = []
    for trip in trips:
        # Get trip-specific expenses
        trip_expenses = Expense.objects.filter(
            expense_level=Expense.ExpenseLevel.TRIP,
            trip=trip
        ).aggregate(
            total_expenses=Sum('amount')
        )['total_expenses'] or Decimal('0.00')

        # For trip profitability, we only include direct trip costs
        # Truck and business expenses are allocated at higher levels
        revenue = trip.transport_amount or Decimal('0.00')
        fuel_cost = trip.fuel_total_cost or Decimal('0.00')
        direct_costs = fuel_cost + trip_expenses
        profit = revenue - direct_costs
        margin = (profit / revenue * 100) if revenue > 0 else Decimal('0.00')

        trips_with_profit.append({
            'trip': trip,
            'revenue': revenue,
            'fuel_cost': fuel_cost,
            'trip_expenses': trip_expenses,
            'direct_costs': direct_costs,
            'profit': profit,
            'margin': margin,
            'revenue_per_ton': (revenue / trip.weight_tons) if trip.weight_tons and trip.weight_tons > 0 else Decimal(
                '0.00'),
            'cost_per_ton': (direct_costs / trip.weight_tons) if trip.weight_tons and trip.weight_tons > 0 else Decimal(
                '0.00')
        })

    # Sort by margin (most profitable first)
    trips_with_profit.sort(key=lambda x: x['margin'], reverse=True)

    # Calculate totals for the filtered queryset
    totals = {
        'total_revenue': sum(t['revenue'] for t in trips_with_profit),
        'total_direct_costs': sum(t['direct_costs'] for t in trips_with_profit),
        'total_profit': sum(t['profit'] for t in trips_with_profit),
        'trip_count': len(trips_with_profit),
    }

    if totals['total_revenue'] > 0:
        totals['avg_margin'] = (totals['total_profit'] / totals['total_revenue'] * 100)
    else:
        totals['avg_margin'] = Decimal('0.00')

    # Pagination
    paginator = Paginator(trips_with_profit, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'page_obj': page_obj,
        'totals': totals,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'truck_filter': truck_filter,
        'transporter_filter': transporter_filter,
        'trucks': Truck.objects.filter(is_active=True).order_by('truck_number'),
        'transporters': Transporter.objects.filter(is_active=True).order_by('name'),
    }

    if request.htmx:
        return render(request, 'admin/trucks/partials/_trip_profitability.html', context)
    return render(request, 'admin/trucks/trip_profitability.html', context)


@login_required
def analytics_api_chart_data(request):
    """API endpoint for chart data"""
    chart_type = request.GET.get('type')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    if not all([chart_type, start_date, end_date]):
        return JsonResponse({'error': 'Missing parameters'}, status=400)

    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format'}, status=400)

    if chart_type == 'profit_trend':
        data = get_profit_trends(start_date, end_date)
        chart_data = {
            'labels': [item['week'].strftime('%Y-%m-%d') for item in data],
            'datasets': [
                {
                    'label': 'Revenue',
                    'data': [float(item['revenue'] or 0) for item in data],
                    'borderColor': 'rgb(54, 162, 235)',
                    'backgroundColor': 'rgba(54, 162, 235, 0.2)',
                },
                {
                    'label': 'Gross Profit',
                    'data': [float(item['gross_profit'] or 0) for item in data],
                    'borderColor': 'rgb(255, 206, 86)',
                    'backgroundColor': 'rgba(255, 206, 86, 0.2)',
                },
                {
                    'label': 'Net Profit',
                    'data': [float(item['net_profit'] or 0) for item in data],
                    'borderColor': 'rgb(75, 192, 192)',
                    'backgroundColor': 'rgba(75, 192, 192, 0.2)',
                }
            ]
        }
        return JsonResponse(chart_data)

    elif chart_type == 'expense_breakdown':
        metrics = get_business_metrics(start_date, end_date)
        chart_data = {
            'labels': ['Fuel Costs', 'Business Expenses', 'Truck Expenses', 'Trip Expenses'],
            'datasets': [{
                'data': [
                    float(metrics['total_fuel_cost']),
                    float(metrics['business_expenses']),
                    float(metrics['truck_expenses']),
                    float(metrics['trip_expenses'])
                ],
                'backgroundColor': [
                    'rgba(255, 99, 132, 0.8)',
                    'rgba(54, 162, 235, 0.8)',
                    'rgba(255, 206, 86, 0.8)',
                    'rgba(75, 192, 192, 0.8)'
                ]
            }]
        }
        return JsonResponse(chart_data)

    return JsonResponse({'error': 'Unknown chart type'}, status=400)


# Additional utility function for expense analysis
def get_expense_analysis_by_category(start_date, end_date, expense_level=None):
    """Get expense breakdown by category and level"""
    filters = {'date__range': [start_date, end_date]}
    if expense_level:
        filters['expense_level'] = expense_level

    return Expense.objects.filter(**filters).values(
        'expense_level', 'category__name'
    ).annotate(
        total_amount=Sum('amount'),
        expense_count=Count('id')
    ).order_by('expense_level', '-total_amount')

