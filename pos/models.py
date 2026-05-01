from django.db import models
from accounts.models import User
from django.utils import timezone
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db.models import F, Sum
from difflib import SequenceMatcher
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey

# ==============================================================================
# 1. CORE & MENU MODELS
# ==============================================================================


class Category(models.Model):
    """
    Represents item categories (e.g., 'Main Course', 'Grill', 'Beers').
    Each category is assigned to a primary module for routing orders to displays.
    """

    class Module(models.TextChoices):
        KITCHEN = 'Kitchen', 'Kitchen'
        BAR = 'Bar', 'Bar'
        BUTCHERY = 'Butchery', 'Butchery'

    name = models.CharField(max_length=100, unique=True)
    module = models.CharField(max_length=50, choices=Module.choices)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return f"{self.name} ({self.get_module_display()})"


class Supplier(models.Model):
    """A supplier for the restaurant."""

    class Status(models.TextChoices):
        ACTIVE = 'Active', 'Active'
        INACTIVE = 'Inactive', 'Inactive'
    name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=255, blank=True)
    phone_number = models.CharField(max_length=20)
    supplies_to = models.CharField(max_length=50, choices=Category.Module.choices)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ACTIVE,
        help_text="Set to 'Inactive' to hide from new purchase orders."
    )

    def __str__(self):
        return self.name


class MenuItem(models.Model):
    """
    A single sellable or trackable item. This model now supports both simple items
    (ingredients, direct sale items) and complex recipes made from multiple ingredients.
    """

    class UnitOfMeasure(models.TextChoices):
        KILOGRAMS = 'kg', 'Kilograms'
        GRAMS = 'g', 'Grams'
        LITERS = 'l', 'Liters'
        MILLILITERS = 'ml', 'Milliliters'
        PIECES = 'pc', 'Pieces'

    unit_of_measure = models.CharField(
        max_length=10,
        choices=UnitOfMeasure.choices,
        default=UnitOfMeasure.PIECES,
        help_text="The unit this item is measured in for inventory purposes."
    )
    image = models.ImageField(
        upload_to='menu_item_images/',
        blank=True,
        null=True,
        help_text="Optional image for the menu item, displayed on the POS."
    )
    name = models.CharField(max_length=255, unique=True, help_text="Always saved in uppercase.")
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='menu_items'
    )

    # --- NEW: Distinguishes finished dishes from raw ingredients ---
    is_recipe = models.BooleanField(
        default=False,
        help_text="Check this if this item is a finished dish made from other ingredients."
    )

    # --- NEW: Many-to-Many relationship for multi-ingredient recipes ---
    ingredients = models.ManyToManyField(
        'self',
        through='RecipeIngredient',
        symmetrical=False,
        related_name='used_in_dishes',
        blank=True
    )

    # --- PRICING & STOCK ---
    selling_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Final price to customer (for menu dishes or direct sale items)."
    )
    supplier_cost_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Cost price from the supplier (for raw materials)."
    )
    stock_quantity = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Physical stock on hand. Only tracked for raw materials and direct sale items."
    )
    low_stock_threshold = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="When stock quantity reaches this level, an alert will be triggered."
    )
    sell_by_weight = models.BooleanField(default=False,
                                         help_text="Can be sold by total amount (e.g., 'KES 700 of beef')")
    is_active = models.BooleanField(default=True, help_text="Is the item available for sale or use?")
    preferred_supplier = models.ForeignKey(
        Supplier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="The default supplier to reorder this item from."
    )
    reorder_quantity = models.DecimalField(
        max_digits=10, decimal_places=2, default=10,
        help_text="The default quantity to order when stock is low."
    )

    def clean(self):
        if self.selling_price < self.supplier_cost_price:
            raise ValidationError("Selling price cannot be less than cost price")
        # Self-reference check moved to RecipeIngredient

    def save(self, *args, **kwargs):
        if self.name:
            self.name = self.name.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @classmethod
    def normalize_name(cls, name):
        """Normalize name for comparison: lowercase, strip, single spaces."""
        return ' '.join(name.strip().lower().split())

    @classmethod
    def find_duplicates(cls, similarity_threshold=0.85):
        """
        Find duplicate or near-duplicate menu items.
        Works efficiently on SQLite by minimizing comparisons.
        """
        from difflib import SequenceMatcher

        # Only consider active items with a name
        items = list(
            cls.objects.filter(is_active=True)
            .only('id', 'name')
            .order_by('name')
        )

        if not items:
            return []

        duplicates = []
        processed = set()

        # First pass: group by normalized name (exact matches)
        norm_groups = {}
        for item in items:
            norm = cls.normalize_name(item.name)
            if norm not in norm_groups:
                norm_groups[norm] = []
            norm_groups[norm].append(item)

        # Handle exact duplicates
        for norm, group in norm_groups.items():
            if len(group) > 1:
                duplicates.append({
                    'primary': group[0],
                    'duplicates': group[1:],
                    'total_count': len(group),
                    'names': [i.name for i in group]
                })
                for item in group:
                    processed.add(item.id)

        # Second pass: fuzzy match only unprocessed items
        unprocessed = [item for item in items if item.id not in processed]
        n = len(unprocessed)

        for i in range(n):
            primary = unprocessed[i]
            if primary.id in processed:
                continue
            fuzzy_group = [primary]
            for j in range(i + 1, n):
                candidate = unprocessed[j]
                if candidate.id in processed:
                    continue
                sim = SequenceMatcher(
                    None,
                    cls.normalize_name(primary.name),
                    cls.normalize_name(candidate.name)
                ).ratio()
                if sim >= similarity_threshold:
                    fuzzy_group.append(candidate)
                    processed.add(candidate.id)
            if len(fuzzy_group) > 1:
                duplicates.append({
                    'primary': fuzzy_group[0],
                    'duplicates': fuzzy_group[1:],
                    'total_count': len(fuzzy_group),
                    'names': [i.name for i in fuzzy_group]
                })
                processed.add(primary.id)

        return duplicates

    @classmethod
    def get_duplicate_stats(cls):
        """Get summary statistics about duplicates"""
        duplicates = cls.find_duplicates()
        total_duplicates = sum(group['total_count'] - 1 for group in duplicates)

        return {
            'duplicate_groups': len(duplicates),
            'total_duplicates': total_duplicates,
            'groups': duplicates
        }


class RecipeIngredient(models.Model):
    """
    This is the "through" model that connects a finished dish (a MenuItem)
    to its ingredients (also MenuItems), and stores the quantity required.
    """
    dish = models.ForeignKey(
        MenuItem,
        on_delete=models.CASCADE,
        related_name='recipe_items', # Allows dish.recipe_items.all()
        limit_choices_to={'is_recipe': True}, # A dish must be a recipe
        verbose_name="Finished Dish"
    )
    ingredient = models.ForeignKey(
        MenuItem,
        on_delete=models.PROTECT,
        related_name='ingredient_for',
        limit_choices_to={'is_recipe': False} # An ingredient cannot be a recipe itself
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3, # Allows for grams (e.g., 0.150 Kg)
        help_text="Quantity of the ingredient required for one serving of the dish."
    )

    class Meta:
        unique_together = ('dish', 'ingredient')
        verbose_name = "Recipe Ingredient"
        verbose_name_plural = "Recipe Ingredients"

    def __str__(self):
        return f"{self.quantity} of {self.ingredient.name} for {self.dish.name}"


class Table(models.Model):
    """ Represents a single physical table in the restaurant. """

    class Status(models.TextChoices):
        AVAILABLE = 'Available', 'Available'
        OCCUPIED = 'Occupied', 'Occupied'
        NEEDS_BILL = 'Needs Bill', 'Needs Bill'

    class Shape(models.TextChoices):
        SQUARE = 'square', 'Square'
        RECTANGLE = 'rectangle', 'Rectangle'
        ROUND = 'round', 'Round'

    table_number = models.CharField(
        max_length=50, unique=True,
        help_text="e.g., 'Table 1', 'Bar Seat 3', 'Patio 5'"
    )
    capacity = models.PositiveIntegerField(default=4)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)
    is_active = models.BooleanField(default=True)

    # --- NEW FIELDS ---
    shape = models.CharField(max_length=10, choices=Shape.choices, default=Shape.SQUARE)
    position_x = models.IntegerField(default=0, help_text="X-coordinate for drag layout.")
    position_y = models.IntegerField(default=0, help_text="Y-coordinate for drag layout.")
    # -------------------

    class Meta:
        ordering = ['table_number']

    def __str__(self):
        return self.table_number


class StockAlert(models.Model):
    """
    Model to track low stock alerts for menu items
    """

    class Status(models.TextChoices):
        ACTIVE = 'Active', 'Active'
        DISMISSED = 'Dismissed', 'Dismissed'  # Used by your existing views
        RESOLVED = 'Resolved', 'Resolved'  # Alternative status

    menu_item = models.ForeignKey(
        'MenuItem',
        on_delete=models.CASCADE,
        related_name='stock_alerts'
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ACTIVE
    )
    stock_level_at_alert = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Stock level when the alert was created"
    )
    created_at = models.DateTimeField(default=timezone.now)

    # Fields for dismissal tracking (used by your existing views)
    dismissed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dismissed_alerts'
    )
    dismissed_at = models.DateTimeField(null=True, blank=True)

    # Optional notes field
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['menu_item', 'status']),
        ]

    def __str__(self):
        return f"Stock Alert: {self.menu_item.name} - {self.status}"

    def dismiss(self, user):
        """Mark the alert as dismissed by a specific user"""
        self.status = self.Status.DISMISSED
        self.dismissed_by = user
        self.dismissed_at = timezone.now()
        self.save()

    def resolve(self):
        """Mark the alert as resolved (alternative to dismissed)"""
        self.status = self.Status.RESOLVED
        self.dismissed_at = timezone.now()
        self.save()


class Customer(models.Model):
    """
    Customer information, with tracking for credit balances.
    """
    name = models.CharField(max_length=255, default="Walking In")
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    credit_balance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Customer's outstanding debt.",
    )
    credit_limit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="The maximum credit amount that can be extended to this customer.",
    )
    loyalty_points = models.PositiveIntegerField(
        default=0,
        help_text="The customer's current loyalty point balance.",
    )

    def __str__(self) -> str:
        return self.name


# ==============================================================================
# 2. ORDER, SALE, & PAYMENT MODELS
# ==============================================================================

class Order(models.Model):
    """
    An order created by a waiter, containing items for a customer.
    Includes subtotals and taxes for accurate billing.
    """

    class Status(models.TextChoices):
        PENDING = 'Pending', 'Pending'
        READY = 'Ready', 'Ready'
        COMPLETED = 'Completed', 'Completed'
        CANCELLED = 'Cancelled', 'Cancelled'

    waiter = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, default=1)
    table = models.ForeignKey(
        'Table',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
        help_text="The table this order is for. Leave blank for takeaway."
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    # --- FINANCIAL FIELDS ---
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    vat_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    service_charge_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    cancellation_auth_code = models.CharField(
        max_length=6,
        blank=True,
        null=True,
        help_text="6-digit code for manager authorization of cancellation"
    )
    cancellation_requested_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the waiter requested cancellation"
    )
    cancellation_requested_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cancellation_requests',
        help_text="Waiter who requested cancellation"
    )
    @property
    def total_items_count(self):
        """Returns the total number of items in this order."""
        return self.items.count()

    @property
    def has_pending_cancellation_request(self):
        """Returns True if a valid cancellation request exists (within 10 minutes)."""
        if not self.cancellation_auth_code or not self.cancellation_requested_at:
            return False
        from django.utils import timezone
        return self.cancellation_requested_at >= timezone.now() - timezone.timedelta(minutes=10)
    @property
    def ready_items_count(self):
        """Returns the number of items in this order that are marked as 'Ready'."""
        return self.items.filter(status=OrderItem.Status.READY).count()

    @property
    def total_amount(self):
        return self.subtotal + self.vat_amount + self.service_charge_amount

    def __str__(self):
        return f"Order #{self.id} for {self.table.table_number if self.table else 'Takeaway'} - {self.status}"


class OrderItem(models.Model):
    """
    A single line item within an Order. Stores the price at the time of sale
    and its preparation status.
    """
    # HIGHLIGHT: Status added to track item progress for Kitchen/Bar displays.
    class Status(models.TextChoices):
        PENDING = 'Pending', 'Pending'
        PREPARING = 'Preparing', 'Preparing'
        READY = 'Ready', 'Ready'
        SERVED = 'Served', 'Served'

    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)  # ← Add this

    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1.0)
    price_at_sale = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    def save(self, *args, **kwargs):
        # ALWAYS recalculate – creation or update
        self.subtotal = self.quantity * self.price_at_sale
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quantity} x {self.menu_item.name} in Order #{self.order.id}"


class Sale(models.Model):
    """
    A finalized, paid order. This is the primary record for financial reporting.
    """

    class PaymentMethod(models.TextChoices):
        CASH = 'Cash', 'Cash'
        MPESA = 'Mpesa', 'M-Pesa'
        CREDIT = 'Credit', 'Credit'

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="sales")
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    processed_at = models.DateTimeField(default=timezone.now)
    mpesa_transaction_id = models.CharField(max_length=50, blank=True, null=True)

    def __str__(self):
        return f"Sale #{self.id} for Order #{self.order.id}"

# ==============================================================================
# 3. INVENTORY, SUPPLIER & INTERNAL TRANSFER MODELS
# ==============================================================================


class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'Draft', 'Draft'
        PENDING = 'Pending', 'Pending'
        PARTIALLY_RECEIVED = 'Partially Received', 'Partially Received'
        FULLY_RECEIVED = 'Fully Received', 'Fully Received'

    class Section(models.TextChoices):
        BAR = 'Bar', 'Bar'
        BUTCHERY = 'Butchery', 'Butchery'

    supplier = models.ForeignKey('Supplier', on_delete=models.PROTECT)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="pos_purchase_orders")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    order_date = models.DateField(default=timezone.now)
    notes = models.TextField(blank=True)
    requested_for_section = models.CharField(max_length=20, choices=Section.choices, default='Bar')

    @property
    def total_ordered_quantity(self):
        return self.items.aggregate(total=Sum('quantity_ordered'))['total'] or Decimal('0')

    @property
    def total_received_quantity(self):
        return self.items.aggregate(total=Sum('quantity_received'))['total'] or Decimal('0')

    @property
    def completion_percentage(self):
        if self.total_ordered_quantity == 0:
            return 0
        return (self.total_received_quantity / self.total_ordered_quantity) * 100

    def update_status(self):
        if self.status == self.Status.DRAFT:
            return  # Don't overwrite draft status

        if self.completion_percentage >= 100:
            self.status = self.Status.FULLY_RECEIVED
        elif self.completion_percentage > 0:
            self.status = self.Status.PARTIALLY_RECEIVED
        else:
            self.status = self.Status.PENDING

        self.save()

    def __str__(self):
        return f"PO #{self.id} to {self.supplier.name} - {self.status}"


class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, related_name='items', on_delete=models.CASCADE)
    menu_item = models.ForeignKey('MenuItem', on_delete=models.PROTECT)
    quantity_ordered = models.DecimalField(max_digits=10, decimal_places=2)
    quantity_received = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)

    @property
    def total_cost(self):
        return self.quantity_ordered * self.unit_price

    @property
    def quantity_remaining(self):
        return max(self.quantity_ordered - self.quantity_received, Decimal('0'))

    @property
    def completion_percentage(self):
        if self.quantity_ordered == 0:
            return 0
        return (self.quantity_received / self.quantity_ordered) * 100

    def save(self, *args, **kwargs):
        if not self.pk:  # New record
            self.unit_price = self.menu_item.supplier_cost_price
        super().save(*args, **kwargs)
        self.purchase_order.update_status()

    def __str__(self):
        return f"{self.quantity_ordered}x {self.menu_item.name} (Received: {self.quantity_received})"


class Delivery(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, related_name='deliveries', on_delete=models.CASCADE, blank=True, null=True)
    supplier = models.ForeignKey('Supplier', on_delete=models.PROTECT)
    delivery_note = models.CharField(max_length=255, blank=True)
    received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    received_at = models.DateTimeField(default=timezone.now)

    @property
    def total_quantity(self):
        return self.items.aggregate(total=Sum('quantity_received'))['total'] or Decimal('0')

    def __str__(self):
        return f"Delivery #{self.id} for PO {self.purchase_order.id}"


class DeliveryItem(models.Model):
    delivery = models.ForeignKey('Delivery', related_name='items', on_delete=models.CASCADE)
    menu_item = models.ForeignKey('MenuItem', on_delete=models.PROTECT)
    quantity_received = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    def save(self, *args, **kwargs):
        # --- THIS IS THE FIX ---
        # We directly add the received quantity to the menu item's stock.
        # The F() object is not needed here.
        self.menu_item.stock_quantity += self.quantity_received
        self.menu_item.save(update_fields=['stock_quantity'])  # More efficient save

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quantity_received}x {self.menu_item.name}"


class StockTransfer(models.Model):
    """
    An internal requisition for stock.
    """

    class Section(models.TextChoices):
        BUTCHERY = 'Butchery', 'Butchery'
        GRILL = 'Grill', 'Grill'
        BAR = 'Bar', 'Bar'

    class Status(models.TextChoices):
        REQUESTED = 'Requested', 'Requested'
        FULFILLED = 'Fulfilled', 'Fulfilled'
        REJECTED = 'Rejected', 'Rejected'

    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED)
    requested_from = models.CharField(max_length=50, choices=Section.choices)
    requested_by_section = models.CharField(max_length=50, choices=Section.choices)
    requested_by_user = models.ForeignKey(User, related_name='stock_requests_made', on_delete=models.SET_NULL,
                                          null=True)
    fulfilled_by_user = models.ForeignKey(User, related_name='stock_requests_fulfilled', on_delete=models.SET_NULL,
                                          null=True, blank=True)
    cost_at_transfer = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    total_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    request_timestamp = models.DateTimeField(default=timezone.now)
    fulfillment_timestamp = models.DateTimeField(null=True, blank=True)
    transferred_to_user = models.ForeignKey(
        User,
        related_name='transfers_received',  # Unique related_name
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        # Optional: Restrict choices in forms/admin
        # limit_choices_to={'role': 'kitchen_staff'} # Adjust 'kitchen_staff' to match your User.ROLE_CHOICES
    )

    @property
    def calculated_amount(self):
        """Calculate the monetary value of this transfer"""
        return self.quantity * self.menu_item.selling_price

    def __str__(self):
        return f"Request for {self.quantity} of {self.menu_item.name} ({self.status})"


# ==============================================================================
# 4. REPORTING MODELS
# ==============================================================================

class InventorySnapshot(models.Model):
    """
    A snapshot of the stock level and value for an item at the end of a day.
    """
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT)
    snapshot_date = models.DateField()
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    total_value = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ('menu_item', 'snapshot_date')
        ordering = ['-snapshot_date', 'menu_item__name']

    def __str__(self):
        return f"{self.menu_item.name} closing stock for {self.snapshot_date}: {self.quantity}"


class CustomerPayment(models.Model):
    """
    Records a payment made by a customer specifically to clear their
    outstanding credit balance. This is NOT a sale, but a debt settlement.
    """

    class PaymentMethod(models.TextChoices):
        CASH = 'Cash', 'Cash'
        MPESA = 'Mpesa', 'M-Pesa'
        # Note: 'Credit' is intentionally not a payment method here,
        # as you cannot pay off debt with more debt.

    # Links the payment to the specific customer
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,  # Prevents deleting a customer with payment history
        related_name='payments'
    )

    # The amount of money that was paid in this transaction
    amount_paid = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    # How the customer settled the debt
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices
    )

    # Automatically records when the payment was made
    payment_date = models.DateTimeField(
        default=timezone.now
    )

    # Tracks which staff member processed this payment for accountability
    processed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,  # If a staff user is deleted, keep the record
        null=True,
        related_name='processed_customer_payments'
    )

    class Meta:
        # Show the most recent payments first by default
        ordering = ['-payment_date']

    def __str__(self):
        return f"Payment of {self.amount_paid} by {self.customer.name} on {self.payment_date.strftime('%Y-%m-%d')}"


class LoyaltySettings(models.Model):
    """
    A singleton model to hold the global rules for the loyalty program.
    There should only ever be one record/row for this model.
    """
    points_per_kes = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=100.00,
        help_text="Amount in KES a customer must spend to earn 1 point. E.g., 100."
    )
    kes_per_point = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1.00,
        help_text="Value of 1 loyalty point in KES during redemption. E.g., 1.00."
    )
    minimum_redeemable_points = models.PositiveIntegerField(
        default=50,
        help_text="The minimum number of points a customer must have to be able to redeem."
    )
    is_active = models.BooleanField(default=True, help_text="Turn the entire loyalty system on or off.")

    def __str__(self):
        return "Loyalty Program Settings"

    class Meta:
        verbose_name_plural = "Loyalty Settings"


class WaiterRewardSettings(models.Model):
    """
    A singleton model to hold the global rules for the waiter reward program.
    There should only ever be one record/row for this model.
    """
    points_per_kes = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=100.00,
        help_text="Amount in KES a waiter's sale must be to earn 1 point. E.g., 100."
    )
    kes_per_point = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1.00,
        help_text="Monetary value of 1 waiter point (for future redemption or bonus calculation). E.g., 1.00."
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Turn the entire waiter reward system on or off."
    )

    # NEW: Leaderboard bonus points
    gold_bonus_points = models.PositiveIntegerField(
        default=500,
        help_text="Bonus points awarded to 1st place waiter"
    )
    silver_bonus_points = models.PositiveIntegerField(
        default=300,
        help_text="Bonus points awarded to 2nd place waiter"
    )
    bronze_bonus_points = models.PositiveIntegerField(
        default=150,
        help_text="Bonus points awarded to 3rd place waiter"
    )
    leaderboard_reset_frequency = models.CharField(
        max_length=20,
        choices=[
            ('daily', 'Daily'),
            ('weekly', 'Weekly'),
            ('monthly', 'Monthly'),
        ],
        default='weekly',
        help_text="How often the leaderboard resets (for display purposes - bonuses are always live)"
    )

    def __str__(self):
        return "Waiter Reward Program Settings"

    class Meta:
        verbose_name_plural = "Waiter Reward Settings"

    def save(self, *args, **kwargs):
        # Ensure only one instance exists
        if WaiterRewardSettings.objects.exists() and not self.pk:
            raise ValidationError("Only one WaiterRewardSettings instance is allowed.")
        return super(WaiterRewardSettings, self).save(*args, **kwargs)

class Coupon(models.Model):
    class DiscountType(models.TextChoices):
        PERCENTAGE = 'Percentage', 'Percentage Off'
        FIXED_AMOUNT = 'Fixed', 'Fixed Amount Off (KES)'

    code = models.CharField(
        max_length=50,
        unique=True,
        help_text="The unique code customers will enter (e.g., 'JULI-20' or 'APOLOGY-XYZ123')."
    )
    description = models.TextField(blank=True, help_text="Internal note about this coupon's purpose.")

    discount_type = models.CharField(max_length=20, choices=DiscountType.choices)
    value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="The percentage (e.g., 10 for 10%) or the fixed amount in KES."
    )

    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField(help_text="The coupon is valid up to the end of this day.")

    max_uses = models.PositiveIntegerField(default=1, help_text="Max number of times this coupon can be used in total.")
    times_used = models.PositiveIntegerField(default=0, editable=False)

    is_active = models.BooleanField(default=True)

    # def __str__(self):
    #     # PROBLEM: This line, while looking safe, was causing the infinite loop in the admin.
    #     return f"{self.code} ({self.get_discount_type_display} - {self.value})"

    def __str__(self):
        # FIX: A safe __str__ method should only reference direct attributes.
        # This version is safe and will not cause a recursion error.
        # It will display cleanly in the Django admin as just the coupon code.
        return self.code


class ExpenseCategory(models.Model):
    """
    Categories for expenses, e.g., 'Utilities', 'Salaries', 'Rent'.
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name_plural = "Expense Categories"
        ordering = ['name']

    def __str__(self):
        return self.name


class AuditLog(models.Model):
    """
    Centralized logging for critical system actions including price changes,
    stock adjustments, and order cancellations.
    """
    class ActionType(models.TextChoices):
        PRICE_CHANGE = 'Price Change', 'Price Change'
        STOCK_ADJUST = 'Stock Adjustment', 'Stock Adjustment'
        ORDER_CANCEL = 'Order Cancellation', 'Order Cancellation'
        DELIVERY = 'Delivery Received', 'Delivery Received'
        EXPENSE = 'Expense Recorded', 'Expense Recorded'
        PAYROLL = 'Payroll Processed', 'Payroll Processed'
        TRANSFER = 'Stock Transfer', 'Stock Transfer'
        GENERAL = 'General', 'General'

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audit_logs')
    action_type = models.CharField(max_length=50, choices=ActionType.choices)
    description = models.TextField()
    
    # Generic relation to track any object
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True)
    object_id = models.CharField(max_length=255, null=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    
    data_before = models.JSONField(null=True, blank=True)
    data_after = models.JSONField(null=True, blank=True)
    
    variance = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name_plural = 'Audit Logs'
        indexes = [
            models.Index(fields=['action_type', '-timestamp']),
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        user_name = self.user.get_full_name() if self.user else 'System'
        return f"{self.action_type} - {user_name} at {self.timestamp}"


class Expense(models.Model):
    """
    Records a single business expense transaction.
    """

    class PaymentMethod(models.TextChoices):
        CASH = 'Cash', 'Cash'
        MPESA_PAYBILL = 'M-Pesa Paybill', 'M-Pesa Paybill'
        BANK_TRANSFER = 'Bank Transfer', 'Bank Transfer'

    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.PROTECT,  # Prevent deleting a category with expenses
        related_name='expenses'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(help_text="A brief description of the expense, e.g., 'KPLC bill for May 2025'.")
    expense_date = models.DateField(default=timezone.now)
    payment_method = models.CharField(max_length=50, choices=PaymentMethod.choices)

    # Optional but highly recommended for record-keeping
    receipt_image = models.ImageField(upload_to='expense_receipts/', blank=True, null=True)

    recorded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='recorded_expenses'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-expense_date']

    def __str__(self):
        return f"{self.category.name} - {self.amount} KES on {self.expense_date}"

