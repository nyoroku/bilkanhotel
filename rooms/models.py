from django.db import models
from django.conf import settings
from django.utils import timezone


class Room(models.Model):
    """Represents a physical room in the property."""

    class RoomType(models.TextChoices):
        SINGLE = 'single', 'Single'
        DOUBLE = 'double', 'Double'
        SUITE = 'suite', 'Suite'
        DELUXE = 'deluxe', 'Deluxe'

    class Status(models.TextChoices):
        AVAILABLE = 'available', 'Available'
        OCCUPIED = 'occupied', 'Occupied'
        MAINTENANCE = 'maintenance', 'Maintenance'

    number = models.CharField(max_length=10, unique=True, help_text="Room number, e.g. 101")
    room_type = models.CharField(max_length=20, choices=RoomType.choices, default=RoomType.SINGLE)
    price_per_night = models.DecimalField(max_digits=10, decimal_places=2)
    floor = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)
    description = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['number']

    def __str__(self):
        return f"Room {self.number} ({self.get_room_type_display()})"


class Booking(models.Model):
    """Represents a guest booking / stay."""

    class PaymentStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PARTIAL = 'partial', 'Partial'
        PAID = 'paid', 'Paid'

    class BookingStatus(models.TextChoices):
        ACTIVE = 'active', 'Active'
        CHECKED_OUT = 'checked_out', 'Checked Out'
        CANCELLED = 'cancelled', 'Cancelled'

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='bookings')
    guest_name = models.CharField(max_length=200)
    guest_phone = models.CharField(max_length=20, blank=True, default='')
    guest_id_number = models.CharField(max_length=50, blank=True, default='', help_text="National ID or Passport")
    check_in = models.DateTimeField(default=timezone.now)
    check_out = models.DateTimeField(null=True, blank=True)
    nights = models.PositiveIntegerField(default=1)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    status = models.CharField(max_length=20, choices=BookingStatus.choices, default=BookingStatus.ACTIVE)
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='room_bookings_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.guest_name} - Room {self.room.number}"

    @property
    def balance(self):
        return self.total_amount - self.amount_paid

    def save(self, *args, **kwargs):
        # Auto-calculate total if not set
        if self.total_amount == 0 and self.nights > 0:
            self.total_amount = self.room.price_per_night * self.nights
        # Update payment status based on amounts
        if self.amount_paid >= self.total_amount and self.total_amount > 0:
            self.payment_status = self.PaymentStatus.PAID
        elif self.amount_paid > 0:
            self.payment_status = self.PaymentStatus.PARTIAL
        else:
            self.payment_status = self.PaymentStatus.PENDING
        super().save(*args, **kwargs)
