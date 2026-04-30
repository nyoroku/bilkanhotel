from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta


# Custom field for monetary values
class MoneyField(models.DecimalField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_digits', 12)
        kwargs.setdefault('decimal_places', 2)
        kwargs.setdefault('validators', [MinValueValidator(Decimal('0.01'))])
        super().__init__(*args, **kwargs)


# Custom managers
class ActiveManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)



class TripManager(models.Manager):
    def unbilled(self):
        return self.filter(invoice__isnull=True, status='completed')

    def for_period(self, start_date, end_date):
        return self.filter(actual_departure__date__range=[start_date, end_date])

    def for_transporter(self, transporter):
        return self.filter(transporter=transporter)

    def with_relations(self):
        return self.select_related(
            'truck', 'truck__current_driver', 'origin', 'destination',  # ✅ Updated to truck__current_driver
            'transporter', 'cargo_type'
        )


# Base models
class Transporter(models.Model):
    """External transporters or clients"""
    name = models.CharField(
        max_length=200,
        unique=True,
        help_text=_("Transporter name")
    )
    contact_person = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        default="",
        help_text=_("Primary contact person")
    )
    phone = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        default="",
        help_text=_("Contact phone number")
    )
    email = models.EmailField(
        null=True,
        blank=True,
        default="",
        help_text=_("Contact email address")
    )
    address = models.TextField(
        null=True,
        blank=True,
        default="",
        help_text=_("Transporter address")
    )
    postal_address = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        default="",
        help_text=_("Postal address (e.g., P.O. Box)")
    )
    is_active = models.BooleanField(
        default=True,
        help_text=_("Whether the transporter is currently active")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    remarks = models.TextField(
        null=True,
        blank=True,
        default="",
        help_text=_("Additional remarks")
    )

    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        verbose_name = _("Transporter")
        verbose_name_plural = _("Transporters")
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return self.name


class Destination(models.Model):
    """Destination locations"""
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text=_("Destination name")
    )
    region = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        default="",
        help_text=_("Region or state")
    )
    country = models.CharField(
        max_length=100,
        default="Kenya",
        help_text=_("Country")
    )
    coordinates = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        default="",
        help_text=_("GPS coordinates (latitude, longitude)")
    )
    is_active = models.BooleanField(
        default=True,
        help_text=_("Whether the destination is currently active")
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        verbose_name = _("Destination")
        verbose_name_plural = _("Destinations")
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['region']),
        ]

    def __str__(self):
        return f"{self.name}, {self.region or self.country}"


class Driver(models.Model):
    """Driver information"""
    first_name = models.CharField(
        max_length=50,
        help_text=_("Driver's first name")
    )
    last_name = models.CharField(
        max_length=50,
        help_text=_("Driver's last name")
    )
    license_number = models.CharField(
        max_length=50,
        unique=True,
        help_text=_("Driver's license number")
    )
    phone = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        default="",
        help_text=_("Driver's phone number")
    )
    email = models.EmailField(
        null=True,
        blank=True,
        default="",
        help_text=_("Driver's email address")
    )
    is_active = models.BooleanField(
        default=True,
        help_text=_("Whether the driver is currently active")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    remarks = models.TextField(
        null=True,
        blank=True,
        default="",
        help_text=_("Additional remarks")
    )

    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        verbose_name = _("Driver")
        verbose_name_plural = _("Drivers")
        ordering = ['first_name', 'last_name']
        indexes = [
            models.Index(fields=['license_number']),
            models.Index(fields=['first_name', 'last_name']),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class Truck(models.Model):
    """Truck information"""

    class TruckType(models.TextChoices):
        FLATBED = 'flatbed', _('Flatbed')
        TANKER = 'tanker', _('Tanker')
        CONTAINER = 'container', _('Container')
        REFRIGERATED = 'refrigerated', _('Refrigerated')
        DUMP = 'dump', _('Dump Truck')
        OTHER = 'other', _('Other')

    truck_number = models.CharField(
        max_length=20,
        unique=True,
        help_text=_("Unique truck identifier/registration number")
    )
    make = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        default="",
        help_text=_("Truck make (e.g., Mercedes, Volvo)")
    )
    model = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        default="",
        help_text=_("Truck model")
    )
    year = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("Manufacturing year")
    )
    truck_type = models.CharField(
        max_length=20,
        choices=TruckType.choices,
        default=TruckType.FLATBED,
        help_text=_("Type of truck")
    )
    capacity_tons = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text=_("Maximum capacity in tons")
    )
    fuel_tank_capacity = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text=_("Fuel tank capacity in litres")
    )

    # ✅ ADDED: Current driver assigned to this truck
    current_driver = models.ForeignKey(
        Driver,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_trucks',
        help_text=_("Current driver assigned to this truck")
    )

    is_active = models.BooleanField(
        default=True,
        help_text=_("Whether the truck is currently active")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    remarks = models.TextField(
        null=True,
        blank=True,
        default="",
        help_text=_("Additional remarks")
    )

    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        verbose_name = _("Truck")
        verbose_name_plural = _("Trucks")
        ordering = ['truck_number']
        indexes = [
            models.Index(fields=['truck_number']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        make_model = f"{self.make} {self.model}".strip()
        if make_model:
            return f"{self.truck_number} ({make_model})"
        return self.truck_number


class CargoType(models.Model):
    """Types of cargo that can be transported"""
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text=_("Cargo type name")
    )
    description = models.TextField(
        null=True,
        blank=True,
        default="",
        help_text=_("Detailed description of the cargo type")
    )
    unit_of_measure = models.CharField(
        max_length=20,
        default="tons",
        help_text=_("Unit of measurement (tons, cubic meters, pieces, etc.)")
    )
    is_hazardous = models.BooleanField(
        default=False,
        help_text=_("Whether this cargo type is hazardous")
    )
    is_active = models.BooleanField(
        default=True,
        help_text=_("Whether this cargo type is currently active")
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        verbose_name = _("Cargo Type")
        verbose_name_plural = _("Cargo Types")
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return self.name


class InvoiceManager(models.Manager):
    def for_period(self, start_date, end_date):
        return self.filter(period_start__gte=start_date, period_end__lte=end_date)

    def overdue(self):
        return self.filter(
            due_date__lt=timezone.now().date(),
            status__in=['sent', 'partially_paid']
        )

    def pending_payment(self):
        return self.filter(balance__gt=0)


class Invoice(models.Model):
    """Invoice for a transporter for a specific period"""

    class InvoiceStatus(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        SENT = 'sent', _('Sent')
        PAID = 'paid', _('Paid')
        PARTIALLY_PAID = 'partially_paid', _('Partially Paid')
        OVERDUE = 'overdue', _('Overdue')
        CANCELLED = 'cancelled', _('Cancelled')

    invoice_number = models.CharField(
        max_length=50,
        unique=True,
        help_text=_("Unique invoice identifier")
    )
    transporter = models.ForeignKey(
        Transporter,
        on_delete=models.CASCADE,
        related_name='invoices',
        help_text=_("Transporter this invoice is for")
    )
    invoice_date = models.DateField(
        help_text=_("Date when invoice was generated")
    )
    period_start = models.DateField(
        help_text=_("Start date of billing period")
    )
    period_end = models.DateField(
        help_text=_("End date of billing period")
    )
    due_date = models.DateField(
        null=True,
        blank=True,
        help_text=_("Payment due date")
    )
    status = models.CharField(
        max_length=20,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.DRAFT,
        help_text=_("Current invoice status")
    )

    # Financial totals - calculated automatically
    total_transport_amount = MoneyField(
        default=Decimal('0.00'),
        help_text=_("Total transport charges")
    )
    total_fuel_amount = MoneyField(
        default=Decimal('0.00'),
        help_text=_("Total fuel charges")
    )
    total_credits = MoneyField(
        default=Decimal('0.00'),
        help_text=_("Total credits/deductions")
    )
    total_amount = MoneyField(
        default=Decimal('0.00'),
        help_text=_("Total invoice amount")
    )
    amount_paid = MoneyField(
        default=Decimal('0.00'),
        help_text=_("Total amount paid")
    )
    balance = MoneyField(
        default=Decimal('0.00'),
        help_text=_("Outstanding balance")
    )

    remarks = models.TextField(
        null=True,
        blank=True,
        default="",
        help_text=_("Additional remarks for the invoice")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = InvoiceManager()

    class Meta:
        verbose_name = _("Invoice")
        verbose_name_plural = _("Invoices")
        ordering = ['-invoice_date', '-created_at']
        unique_together = [['transporter', 'period_start', 'period_end']]
        indexes = [
            models.Index(fields=['invoice_date']),
            models.Index(fields=['status']),
            models.Index(fields=['transporter', 'invoice_date']),
            models.Index(fields=['period_start', 'period_end']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(period_end__gte=models.F('period_start')),
                name='valid_invoice_period'
            ),
            models.CheckConstraint(
                condition=models.Q(total_amount__gte=0),
                name='positive_total_amount'
            )
        ]

    def clean(self):
        if self.period_start and self.period_end:
            if self.period_start >= self.period_end:
                raise ValidationError("Period start must be before period end")

        if self.due_date and self.invoice_date:
            if self.due_date < self.invoice_date:
                raise ValidationError("Due date cannot be before invoice date")

    def update_status(self):
        """Auto-update invoice status based on balance and payments."""
        if self.balance <= 0:
            self.status = self.InvoiceStatus.PAID
        elif self.amount_paid > 0:
            self.status = self.InvoiceStatus.PARTIALLY_PAID
        # Keep DRAFT/SENT/OVERDUE as-is unless paid

    def calculate_totals(self):
        """Calculate invoice totals from related trip records"""
        from django.db.models import Sum

        # Sum up amounts from all trips
        trip_totals = self.trips.aggregate(
            transport_total=Sum('transport_amount'),
            fuel_total=Sum('fuel_total_cost')  # ✅ Uses fuel_total_cost, not fuel_amount
        )

        # Sum up credits
        credits_total = self.credits.aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')

        # Sum up payments
        payments_total = self.payments.aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')

        self.total_transport_amount = trip_totals['transport_total'] or Decimal('0.00')
        self.total_fuel_amount = trip_totals['fuel_total'] or Decimal('0.00')
        self.total_credits = credits_total
        self.total_amount = self.total_transport_amount + self.total_fuel_amount - self.total_credits
        self.amount_paid = payments_total
        self.balance = self.total_amount - self.amount_paid

        # ✅ Auto-update status
        self.update_status()

    def save(self, *args, **kwargs):
        # Set due date if not provided
        if not self.due_date and self.invoice_date:
            self.due_date = self.invoice_date + timedelta(days=30)

        # Auto-generate invoice number if not set
        if not self.invoice_number:
            transporter_initials = "".join([word[0].upper() for word in self.transporter.name.split()[:3]])
            self.invoice_number = f"INV-{self.invoice_date.strftime('%Y-%m')}-{transporter_initials}"

        # Calculate totals only if the invoice already exists (has an ID)
        if self.pk:
            self.calculate_totals()

        super().save(*args, **kwargs)

    @property
    def is_overdue(self):
        return (
                self.due_date and
                self.due_date < timezone.now().date() and
                self.balance > 0
        )

    @property
    def payment_status(self):
        if self.balance <= 0:
            return "Fully Paid"
        elif self.amount_paid > 0:
            return "Partially Paid"
        else:
            return "Unpaid"

    def __str__(self):
        return f"{self.invoice_number} | {self.transporter.name} | {self.total_amount} | {self.get_status_display()}"


class Trip(models.Model):
    """Main trip record with integrated cargo and fuel information"""

    class TripStatus(models.TextChoices):
        PLANNED = 'planned', _('Planned')
        IN_PROGRESS = 'in_progress', _('In Progress')
        COMPLETED = 'completed', _('Completed')
        CANCELLED = 'cancelled', _('Cancelled')
        DELAYED = 'delayed', _('Delayed')

    class DeliveryStatus(models.TextChoices):
        PENDING = 'pending', _('Pending')
        LOADED = 'loaded', _('Loaded')
        IN_TRANSIT = 'in_transit', _('In Transit')
        DELIVERED = 'delivered', _('Delivered')
        PARTIAL_DELIVERY = 'partial', _('Partial Delivery')
        DAMAGED = 'damaged', _('Damaged')
        LOST = 'lost', _('Lost')
        RETURNED = 'returned', _('Returned')

    # Basic trip information
    trip_number = models.CharField(
        max_length=50,
        unique=True,
        help_text=_("Unique trip identifier")
    )
    truck = models.ForeignKey(
        Truck,
        on_delete=models.CASCADE,
        related_name='trips',
        help_text=_("Truck assigned to this trip")
    )
    driver = models.ForeignKey(
        Driver,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trips',
        help_text=_("Driver assigned to this trip — auto-filled from truck if not specified")
    )
    origin = models.ForeignKey(
        Destination,
        on_delete=models.CASCADE,
        related_name='origin_trips',
        help_text=_("Trip origin location")
    )
    destination = models.ForeignKey(
        Destination,
        on_delete=models.CASCADE,
        related_name='destination_trips',
        help_text=_("Trip destination location")
    )
    transporter = models.ForeignKey(
        Transporter,
        on_delete=models.CASCADE,
        related_name='trips',
        help_text=_("Transporter/client")
    )

    # Scheduling
    planned_departure = models.DateTimeField(
        help_text=_("Planned departure date and time"), null=True,
        blank=True
    )
    actual_departure = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Actual departure date and time")
    )
    planned_arrival = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Planned arrival date and time")
    )
    actual_arrival = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Actual arrival date and time")
    )

    # Cargo information (integrated)
    cargo_type = models.ForeignKey(
        CargoType,
        on_delete=models.CASCADE, null=True, blank=True,
        help_text=_("Type of cargo being transported")
    )
    cargo_description = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        default="",
        help_text=_("Specific cargo description")
    )
    weight_tons = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text=_("Total weight in tons")
    )
    delivered_weight = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0'))],
        default=Decimal('0.00'),
        help_text=_("Actual weight delivered")
    )

    # Financial information
    rate_per_ton = MoneyField(
        help_text=_("Rate per ton"), null=True,
        blank=True
    )
    transport_amount = MoneyField(
        help_text=_("Total transport amount"),  null=True,
        blank=True
    )

    # ✅ ADDED: Fuel information directly on trip
    fuel_litres = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text=_("Total litres of fuel consumed for this trip")
    )
    fuel_cost_per_litre = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text=_("Cost per litre of fuel for this trip")
    )
    fuel_total_cost = MoneyField(
        null=True,
        blank=True,
        help_text=_("Total fuel cost for this trip")
    )

    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=TripStatus.choices,
        default=TripStatus.PLANNED,
        help_text=_("Current trip status")
    )
    delivery_status = models.CharField(
        max_length=20,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.PENDING,
        help_text=_("Delivery status")
    )

    # Additional information
    distance_km = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text=_("Trip distance in kilometers")
    )
    remarks = models.TextField(
        null=True,
        blank=True,
        default="",
        help_text=_("Additional notes about the trip")
    )
    source_document = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        default="",
        help_text=_("Source document reference")
    )

    # Billing relationship
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trips',
        help_text=_("Invoice this trip belongs to")
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TripManager()

    class Meta:
        verbose_name = _("Trip")
        verbose_name_plural = _("Trips")
        ordering = ['-planned_departure', '-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['planned_departure']),
            models.Index(fields=['actual_departure']),
            models.Index(fields=['truck']),
            models.Index(fields=['driver']),
            models.Index(fields=['transporter']),
            models.Index(fields=['invoice']),
        ]

    def clean(self):
        if self.actual_departure and self.actual_arrival:
            if self.actual_departure >= self.actual_arrival:
                raise ValidationError("Departure must be before arrival")

    def save(self, *args, **kwargs):
        # ✅ Auto-set driver from truck if not manually specified
        if self.truck and not self.driver:
            self.driver = self.truck.current_driver

        # Auto-calculate transport amount
        if self.weight_tons and self.rate_per_ton:
            self.transport_amount = self.weight_tons * self.rate_per_ton

        # ✅ Auto-calculate fuel total cost
        if self.fuel_litres and self.fuel_cost_per_litre:
            self.fuel_total_cost = self.fuel_litres * self.fuel_cost_per_litre

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.trip_number}: {self.origin} → {self.destination}"


class FuelRecord(models.Model):
    """Fuel consumption and costs for trips (for detailed logging)"""

    class FuelType(models.TextChoices):
        DIESEL = 'diesel', _('Diesel')
        PETROL = 'petrol', _('Petrol')
        OTHER = 'other', _('Other')

    trip = models.ForeignKey(
        Trip,
        on_delete=models.CASCADE,
        related_name='fuel_records',
        help_text=_("Trip this fuel record belongs to")
    )
    date = models.DateField(
        help_text=_("Date of fuel purchase/consumption")
    )
    fuel_type = models.CharField(
        max_length=20,
        choices=FuelType.choices,
        default=FuelType.DIESEL,
        help_text=_("Type of fuel")
    )
    litres = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text=_("Quantity of fuel in litres")
    )
    cost_per_litre = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text=_("Cost per litre of fuel")
    )
    total_cost = MoneyField(
        null=True,
        blank=True,
        help_text=_("Total fuel cost")
    )
    fuel_station = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        default="",
        help_text=_("Fuel station name")
    )
    odometer_reading = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("Odometer reading at time of fueling")
    )
    receipt_number = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        default="",
        help_text=_("Fuel receipt number")
    )
    remarks = models.TextField(
        null=True,
        blank=True,
        default="",
        help_text=_("Additional notes about fuel record")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Fuel Record")
        verbose_name_plural = _("Fuel Records")
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['trip']),
        ]

    def save(self, *args, **kwargs):
        # Auto-calculate total cost
        if self.litres and self.cost_per_litre and not self.total_cost:
            self.total_cost = self.litres * self.cost_per_litre
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.litres}L {self.fuel_type} - {self.date}"


class InvoiceCredit(models.Model):
    """Credits/deductions on an invoice (lost bags, damages, etc.)"""

    class CreditType(models.TextChoices):
        LOST_BAGS = 'lost_bags', _('Lost Bags')
        DAMAGED_GOODS = 'damaged_goods', _('Damaged Goods')
        SHORT_DELIVERY = 'short_delivery', _('Short Delivery')
        FUEL_DEDUCTION = 'fuel_deduction', _('Fuel Deduction')
        OTHER = 'other', _('Other')

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name='credits',
        help_text=_("Invoice this credit belongs to")
    )
    trip = models.ForeignKey(
        Trip,
        on_delete=models.CASCADE,
        related_name='credits',
        null=True,
        blank=True,
        help_text=_("Trip associated with this credit")
    )
    credit_type = models.CharField(
        max_length=20,
        choices=CreditType.choices,
        help_text=_("Type of credit/deduction")
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text=_("Quantity (bags, tons, etc.)")
    )
    amount = MoneyField(
        help_text=_("Credit amount")
    )
    description = models.CharField(
        max_length=200,
        help_text=_("Description of the item/incident")
    )
    remarks = models.TextField(
        null=True,
        blank=True,
        default="",
        help_text=_("Additional remarks")
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Invoice Credit")
        verbose_name_plural = _("Invoice Credits")
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_credit_type_display()}: {self.amount} - {self.description}"


class Payment(models.Model):
    """Payments received against invoices"""

    class PaymentMethod(models.TextChoices):
        CASH = 'cash', _('Cash')
        BANK_TRANSFER = 'bank_transfer', _('Bank Transfer')
        CHEQUE = 'cheque', _('Cheque')
        MOBILE_MONEY = 'mobile_money', _('Mobile Money')
        OTHER = 'other', _('Other')

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name='payments',
        help_text=_("Invoice this payment is for")
    )
    payment_date = models.DateField(
        help_text=_("Date payment was received")
    )
    amount = MoneyField(
        help_text=_("Payment amount")
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.BANK_TRANSFER,
        help_text=_("Method of payment")
    )
    reference_number = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        default="",
        help_text=_("Payment reference number")
    )
    remarks = models.TextField(
        null=True,
        blank=True,
        default="",
        help_text=_("Payment remarks")
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Payment")
        verbose_name_plural = _("Payments")
        ordering = ['-payment_date', '-created_at']
        indexes = [
            models.Index(fields=['payment_date']),
            models.Index(fields=['invoice']),
        ]

    def __str__(self):
        return f"Payment {self.amount} for {self.invoice.invoice_number} ({self.payment_date})"


class ExpenseCategory(models.Model):
    """Categories for different types of expenses"""
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text=_("Expense category name")
    )
    description = models.TextField(
        null=True,
        blank=True,
        default="",
        help_text=_("Description of the expense category")
    )
    is_active = models.BooleanField(
        default=True,
        help_text=_("Whether this category is currently active")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        verbose_name = _("Expense Category")
        verbose_name_plural = _("Expense Categories")
        ordering = ['name']

    def __str__(self):
        return self.name


class Expense(models.Model):
    """Expenses at different levels - trip, truck, or business"""

    class ExpenseLevel(models.TextChoices):
        TRIP = 'trip', _('Trip Level')
        TRUCK = 'truck', _('Truck Level')
        BUSINESS = 'business', _('Business Level')

    # Expense level and relationships
    expense_level = models.CharField(
        max_length=20,
        choices=ExpenseLevel.choices,
        help_text=_("Level at which this expense is tracked")
    )

    # Optional relationships based on expense level
    trip = models.ForeignKey(
        Trip,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='expenses',
        help_text=_("Trip this expense belongs to (for trip-level expenses)")
    )
    truck = models.ForeignKey(
        Truck,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='expenses',
        help_text=_("Truck this expense belongs to (for truck-level expenses)")
    )

    # Expense details
    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.CASCADE,
        related_name='expenses',
        help_text=_("Expense category")
    )
    description = models.CharField(
        max_length=200,
        help_text=_("Description of the expense")
    )
    amount = MoneyField(
        help_text=_("Expense amount")
    )
    date = models.DateField(
        help_text=_("Date of expense")
    )
    receipt_number = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        default="",
        help_text=_("Receipt or reference number")
    )
    vendor = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        default="",
        help_text=_("Vendor or service provider")
    )
    is_recurring = models.BooleanField(
        default=False,
        help_text=_("Whether this is a recurring expense (insurance, permits, etc.)")
    )
    remarks = models.TextField(
        null=True,
        blank=True,
        default="",
        help_text=_("Additional notes about the expense")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Expense")
        verbose_name_plural = _("Expenses")
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['expense_level']),
            models.Index(fields=['trip']),
            models.Index(fields=['truck']),
            models.Index(fields=['category']),
        ]

    def clean(self):
        """Validate that the correct relationship is set based on expense level"""
        if self.expense_level == self.ExpenseLevel.TRIP and not self.trip:
            raise ValidationError(_("Trip must be specified for trip-level expenses"))
        elif self.expense_level == self.ExpenseLevel.TRUCK and not self.truck:
            raise ValidationError(_("Truck must be specified for truck-level expenses"))
        elif self.expense_level == self.ExpenseLevel.BUSINESS and (self.trip or self.truck):
            raise ValidationError(_("Business-level expenses should not be linked to trip or truck"))

        # Ensure only the relevant relationship is set
        if self.expense_level == self.ExpenseLevel.TRIP:
            self.truck = None
        elif self.expense_level == self.ExpenseLevel.TRUCK:
            self.trip = None
        elif self.expense_level == self.ExpenseLevel.BUSINESS:
            self.trip = None
            self.truck = None

    def __str__(self):
        level_info = ""
        if self.expense_level == self.ExpenseLevel.TRIP and self.trip:
            level_info = f" - {self.trip.trip_number}"
        elif self.expense_level == self.ExpenseLevel.TRUCK and self.truck:
            level_info = f" - {self.truck.truck_number}"
        elif self.expense_level == self.ExpenseLevel.BUSINESS:
            level_info = " - Business"
        return f"{self.category.name}: {self.amount} ({self.date}){level_info}"


# Legacy model - for data migration only
class TruckLogisticsRecord(models.Model):
    """
    Legacy model - kept for data migration purposes
    This should be removed after migrating data to the new normalized models
    """

    class TransportStatus(models.TextChoices):
        ON_TRANSIT = 'on_transit', _('On Transit')
        OFFLOADED = 'offloaded', _('Offloaded')
        DID_NOT_LOAD = 'did_not_load', _('Didn\'t Load')
        DELAYED = 'delayed', _('Delayed')
        CANCELLED = 'cancelled', _('Cancelled')

    class DeliveryStatus(models.TextChoices):
        RECEIVED = 'received', _('Received')
        PENDING = 'pending', _('Pending')
        PARTIAL = 'partial', _('Partial')
        LOST = 'lost', _('Lost')
        DAMAGED = 'damaged', _('Damaged')

    # Original fields for migration compatibility
    date = models.DateField(null=True, blank=True)
    truck_number = models.CharField(max_length=20)
    transporter = models.CharField(max_length=100, null=True, blank=True, default="")
    destination = models.CharField(max_length=100, null=True, blank=True, default="")
    tonnage = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=TransportStatus.choices, default=TransportStatus.ON_TRANSIT)
    delivery_status = models.CharField(max_length=20, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING)
    rate_per_ton = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    total_transport_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    litres_of_fuel = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cost_per_litre = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    fuel_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    remarks = models.TextField(null=True, blank=True, default="")
    source_document = models.CharField(max_length=100, null=True, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Legacy Truck Logistics Record")
        verbose_name_plural = _("Legacy Truck Logistics Records")
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"Legacy: {self.truck_number} to {self.destination or 'N/A'} on {self.date or 'Unknown Date'}"

