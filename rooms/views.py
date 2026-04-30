from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum, Q, Count
from datetime import timedelta
from decimal import Decimal
from .models import Room, Booking


def _room_role_required(view_func):
    """Decorator: only admin, manager, or room_manager can access."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:user_login')
        if request.user.role not in ('admin', 'manager', 'room_manager'):
            messages.error(request, "You don't have permission to access rooms management.")
            return redirect('pos:pos')
        return view_func(request, *args, **kwargs)
    return wrapper


@login_required
@_room_role_required
def rooms_dashboard(request):
    """Main rooms dashboard with occupancy and revenue stats."""
    today = timezone.now().date()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)

    # Custom date range
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')

    total_rooms = Room.objects.filter(is_active=True).count()
    occupied = Room.objects.filter(is_active=True, status=Room.Status.OCCUPIED).count()
    available = Room.objects.filter(is_active=True, status=Room.Status.AVAILABLE).count()
    maintenance = Room.objects.filter(is_active=True, status=Room.Status.MAINTENANCE).count()

    # Revenue calculations
    revenue_today = Booking.objects.filter(
        check_in__date=today
    ).aggregate(total=Sum('amount_paid'))['total'] or Decimal('0')

    revenue_week = Booking.objects.filter(
        check_in__date__gte=start_of_week
    ).aggregate(total=Sum('amount_paid'))['total'] or Decimal('0')

    revenue_month = Booking.objects.filter(
        check_in__date__gte=start_of_month
    ).aggregate(total=Sum('amount_paid'))['total'] or Decimal('0')

    # Custom range revenue
    custom_revenue = None
    if start_date_str and end_date_str:
        custom_revenue = Booking.objects.filter(
            check_in__date__gte=start_date_str,
            check_in__date__lte=end_date_str
        ).aggregate(total=Sum('amount_paid'))['total'] or Decimal('0')

    # Active bookings
    active_bookings = Booking.objects.filter(
        status=Booking.BookingStatus.ACTIVE
    ).select_related('room', 'created_by').order_by('-check_in')

    # Recent checkouts
    recent_checkouts = Booking.objects.filter(
        status=Booking.BookingStatus.CHECKED_OUT
    ).select_related('room').order_by('-check_out')[:10]

    context = {
        'total_rooms': total_rooms,
        'occupied': occupied,
        'available': available,
        'maintenance': maintenance,
        'occupancy_rate': round((occupied / total_rooms * 100), 1) if total_rooms > 0 else 0,
        'revenue_today': revenue_today,
        'revenue_week': revenue_week,
        'revenue_month': revenue_month,
        'custom_revenue': custom_revenue,
        'start_date': start_date_str or '',
        'end_date': end_date_str or '',
        'active_bookings': active_bookings,
        'recent_checkouts': recent_checkouts,
    }
    return render(request, 'rooms/rooms_dashboard.html', context)


@login_required
@_room_role_required
def room_list(request):
    """List all rooms with status indicators."""
    rooms = Room.objects.filter(is_active=True).order_by('floor', 'number')
    context = {'rooms': rooms}
    return render(request, 'rooms/room_list.html', context)


@login_required
@_room_role_required
def room_add(request):
    """Add a new room."""
    if request.method == 'POST':
        try:
            room = Room(
                number=request.POST['number'],
                room_type=request.POST['room_type'],
                price_per_night=Decimal(request.POST['price_per_night']),
                floor=int(request.POST.get('floor', 1)),
                description=request.POST.get('description', ''),
            )
            room.save()
            messages.success(request, f'Room {room.number} created successfully.')
            return redirect('rooms:room_list')
        except Exception as e:
            messages.error(request, f'Error creating room: {e}')

    context = {'room_types': Room.RoomType.choices}
    return render(request, 'rooms/room_form.html', context)


@login_required
@_room_role_required
def room_edit(request, pk):
    """Edit an existing room."""
    room = get_object_or_404(Room, pk=pk)
    if request.method == 'POST':
        try:
            room.number = request.POST['number']
            room.room_type = request.POST['room_type']
            room.price_per_night = Decimal(request.POST['price_per_night'])
            room.floor = int(request.POST.get('floor', 1))
            room.status = request.POST.get('status', room.status)
            room.description = request.POST.get('description', '')
            room.save()
            messages.success(request, f'Room {room.number} updated.')
            return redirect('rooms:room_list')
        except Exception as e:
            messages.error(request, f'Error updating room: {e}')

    context = {
        'room': room,
        'room_types': Room.RoomType.choices,
        'status_choices': Room.Status.choices,
    }
    return render(request, 'rooms/room_form.html', context)


@login_required
@_room_role_required
def booking_create(request):
    """Check in a guest — create a new booking."""
    available_rooms = Room.objects.filter(is_active=True, status=Room.Status.AVAILABLE)

    if request.method == 'POST':
        try:
            room = get_object_or_404(Room, pk=request.POST['room'])
            if room.status != Room.Status.AVAILABLE:
                messages.error(request, 'Room is not available.')
                return redirect('rooms:booking_create')

            booking = Booking(
                room=room,
                guest_name=request.POST['guest_name'],
                guest_phone=request.POST.get('guest_phone', ''),
                guest_id_number=request.POST.get('guest_id_number', ''),
                nights=int(request.POST.get('nights', 1)),
                notes=request.POST.get('notes', ''),
                created_by=request.user,
            )
            booking.save()

            # Mark room as occupied
            room.status = Room.Status.OCCUPIED
            room.save()

            messages.success(request, f'Guest {booking.guest_name} checked into Room {room.number}.')
            return redirect('rooms:rooms_dashboard')
        except Exception as e:
            messages.error(request, f'Error creating booking: {e}')

    context = {'available_rooms': available_rooms}
    return render(request, 'rooms/booking_form.html', context)


@login_required
@_room_role_required
def booking_pay(request, pk):
    """Record a payment against a booking."""
    booking = get_object_or_404(Booking, pk=pk)

    if request.method == 'POST':
        try:
            amount = Decimal(request.POST['amount'])
            if amount <= 0:
                messages.error(request, 'Amount must be positive.')
                return redirect('rooms:booking_pay', pk=pk)

            booking.amount_paid += amount
            booking.save()
            messages.success(request, f'Payment of KES {amount:,.2f} recorded for {booking.guest_name}.')
            return redirect('rooms:rooms_dashboard')
        except Exception as e:
            messages.error(request, f'Error recording payment: {e}')

    context = {'booking': booking}
    return render(request, 'rooms/booking_pay.html', context)


@login_required
@_room_role_required
def booking_checkout(request, pk):
    """Check out a guest."""
    booking = get_object_or_404(Booking, pk=pk)

    if request.method == 'POST':
        booking.status = Booking.BookingStatus.CHECKED_OUT
        booking.check_out = timezone.now()
        booking.save()

        # Free up the room
        room = booking.room
        room.status = Room.Status.AVAILABLE
        room.save()

        messages.success(request, f'{booking.guest_name} checked out of Room {room.number}.')
        return redirect('rooms:rooms_dashboard')

    context = {'booking': booking}
    return render(request, 'rooms/booking_checkout.html', context)


