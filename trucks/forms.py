# forms.py (final, updated for auto-driver, fuel fields, and invoice management)
from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils import timezone
from datetime import timedelta
from django.utils.translation import gettext_lazy as _
from decimal import Decimal
from decimal import Decimal, InvalidOperation
from .models import (
    Trip, Invoice, Truck, Destination, Transporter, Driver, CargoType,
    FuelRecord, Expense, ExpenseCategory, Payment, InvoiceCredit,
)


# ------------------------------------------------------------------
#  OPERATIONAL FORMS
# ------------------------------------------------------------------
class TripForm(forms.ModelForm):
    """Single-trip form (replaces old TripRecordForm)."""

    class Meta:
        model = Trip
        fields = [
            'trip_number', 'truck', 'driver', 'origin', 'destination',
            'transporter', 'planned_departure', 'planned_arrival',
            'actual_departure', 'actual_arrival',
            'cargo_type', 'cargo_description', 'weight_tons', 'delivered_weight',
            'rate_per_ton', 'transport_amount',
            # ✅ ADDED: Fuel fields
            'fuel_litres', 'fuel_cost_per_litre', 'fuel_total_cost',
            'distance_km',
            'status', 'delivery_status', 'remarks', 'source_document'
        ]
        widgets = {
            'trip_number': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Auto-generated if empty'}),
            'truck': forms.Select(attrs={'class': 'select'}),
            'driver': forms.Select(attrs={'class': 'select'}),
            'origin': forms.Select(attrs={'class': 'select'}),
            'destination': forms.Select(attrs={'class': 'select'}),
            'transporter': forms.Select(attrs={'class': 'select'}),
            'planned_departure': forms.DateTimeInput(attrs={'class': 'input', 'type': 'datetime-local'}),
            'planned_arrival': forms.DateTimeInput(attrs={'class': 'input', 'type': 'datetime-local'}),
            'actual_departure': forms.DateTimeInput(attrs={'class': 'input', 'type': 'datetime-local'}),
            'actual_arrival': forms.DateTimeInput(attrs={'class': 'input', 'type': 'datetime-local'}),
            'cargo_type': forms.Select(attrs={'class': 'select'}),
            'cargo_description': forms.TextInput(attrs={'class': 'input', 'placeholder': 'e.g. Maize bran'}),
            'weight_tons': forms.NumberInput(attrs={'class': 'input', 'step': '0.01', 'min': '0.01'}),
            'delivered_weight': forms.NumberInput(attrs={'class': 'input', 'step': '0.01', 'min': '0'}),
            'rate_per_ton': forms.NumberInput(attrs={'class': 'input', 'step': '0.01', 'min': '0.01'}),
            'transport_amount': forms.NumberInput(attrs={'class': 'input', 'step': '0.01', 'readonly': True}),
            # ✅ ADDED: Fuel widgets
            'fuel_litres': forms.NumberInput(
                attrs={'class': 'input', 'step': '0.01', 'min': '0.01', 'placeholder': 'Litres used'}),
            'fuel_cost_per_litre': forms.NumberInput(
                attrs={'class': 'input', 'step': '0.01', 'min': '0.01', 'placeholder': 'Cost per litre'}),
            'fuel_total_cost': forms.NumberInput(
                attrs={'class': 'input', 'step': '0.01', 'readonly': True, 'placeholder': 'Auto-calculated'}),
            'distance_km': forms.NumberInput(attrs={'class': 'input', 'step': '0.01', 'min': '0'}),
            'status': forms.Select(attrs={'class': 'select'}),
            'delivery_status': forms.Select(attrs={'class': 'select'}),
            'remarks': forms.Textarea(attrs={'class': 'textarea', 'rows': 3}),
            'source_document': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Loading order / LR number'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter active records only
        self.fields['truck'].queryset = Truck.objects.filter(is_active=True)
        self.fields['driver'].queryset = Driver.objects.filter(is_active=True)
        self.fields['origin'].queryset = Destination.objects.filter(is_active=True)
        self.fields['destination'].queryset = Destination.objects.filter(is_active=True)
        self.fields['transporter'].queryset = Transporter.objects.filter(is_active=True)
        self.fields['cargo_type'].queryset = CargoType.objects.filter(is_active=True)

        # Optional fields
        optional_fields = [
            'driver', 'planned_arrival', 'actual_departure', 'actual_arrival',
            'delivered_weight', 'distance_km', 'remarks', 'source_document',
            'fuel_litres', 'fuel_cost_per_litre'  # Fuel fields are optional
        ]
        for field in optional_fields:
            self.fields[field].required = False

    def validate_decimal_places(self, value, field_name, max_decimal_places=2):
        """Validate that a decimal value doesn't exceed max decimal places."""
        if value is None:
            return value

        try:
            # Convert to Decimal for precise decimal place counting
            decimal_value = Decimal(str(value))

            # Check decimal places
            sign, digits, exponent = decimal_value.as_tuple()
            if exponent < -max_decimal_places:
                raise ValidationError(
                    _(f"{field_name} cannot have more than {max_decimal_places} decimal places.")
                )

            # Round to max decimal places to prevent precision issues
            return decimal_value.quantize(Decimal('0.01'))

        except (ValueError, InvalidOperation):
            raise ValidationError(_(f"Invalid decimal value for {field_name}."))

    def clean_weight_tons(self):
        weight = self.cleaned_data.get('weight_tons')
        return self.validate_decimal_places(weight, 'Weight (tons)')

    def clean_delivered_weight(self):
        weight = self.cleaned_data.get('delivered_weight')
        return self.validate_decimal_places(weight, 'Delivered weight')

    def clean_rate_per_ton(self):
        rate = self.cleaned_data.get('rate_per_ton')
        return self.validate_decimal_places(rate, 'Rate per ton')

    def clean_fuel_litres(self):
        fuel_litres = self.cleaned_data.get('fuel_litres')
        return self.validate_decimal_places(fuel_litres, 'Fuel litres')

    def clean_fuel_cost_per_litre(self):
        fuel_cost = self.cleaned_data.get('fuel_cost_per_litre')
        return self.validate_decimal_places(fuel_cost, 'Fuel cost per litre')

    def clean_distance_km(self):
        distance = self.cleaned_data.get('distance_km')
        return self.validate_decimal_places(distance, 'Distance (km)')

    def clean(self):
        cleaned_data = super().clean()

        # Validate departure/arrival logic
        planned_dep = cleaned_data.get('planned_departure')
        planned_arr = cleaned_data.get('planned_arrival')
        actual_dep = cleaned_data.get('actual_departure')
        actual_arr = cleaned_data.get('actual_arrival')

        if planned_dep and planned_arr and planned_dep >= planned_arr:
            raise ValidationError(_("Planned arrival must be after planned departure."))

        if actual_dep and actual_arr and actual_dep >= actual_arr:
            raise ValidationError(_("Actual arrival must be after actual departure."))

        # Auto-calculate transport amount with proper decimal handling
        weight = cleaned_data.get('weight_tons')
        rate = cleaned_data.get('rate_per_ton')
        if weight and rate:
            try:
                # Ensure both values are Decimal and calculate with proper precision
                weight_decimal = Decimal(str(weight))
                rate_decimal = Decimal(str(rate))
                transport_amount = weight_decimal * rate_decimal
                # Round to 2 decimal places
                cleaned_data['transport_amount'] = transport_amount.quantize(Decimal('0.01'))
            except (ValueError, InvalidOperation):
                raise ValidationError(_("Error calculating transport amount. Please check weight and rate values."))

        # ✅ Auto-calculate fuel total cost with proper decimal handling
        fuel_litres = cleaned_data.get('fuel_litres')
        fuel_cost_per_litre = cleaned_data.get('fuel_cost_per_litre')
        if fuel_litres and fuel_cost_per_litre:
            try:
                # Ensure both values are Decimal and calculate with proper precision
                litres_decimal = Decimal(str(fuel_litres))
                cost_decimal = Decimal(str(fuel_cost_per_litre))
                fuel_total = litres_decimal * cost_decimal
                # Round to 2 decimal places
                cleaned_data['fuel_total_cost'] = fuel_total.quantize(Decimal('0.01'))
            except (ValueError, InvalidOperation):
                raise ValidationError(_("Error calculating fuel total cost. Please check fuel values."))

        # ✅ Auto-set driver from truck if not provided
        truck = cleaned_data.get('truck')
        driver = cleaned_data.get('driver')
        if truck and not driver and hasattr(truck, 'current_driver'):
            cleaned_data['driver'] = truck.current_driver

        return cleaned_data

class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = [
            'invoice_number', 'transporter', 'invoice_date',
            'period_start', 'period_end', 'due_date', 'status', 'remarks'
        ]
        widgets = {
            'invoice_number': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Auto-generated'}),
            'transporter': forms.Select(attrs={'class': 'select'}),
            'invoice_date': forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
            'period_start': forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
            'period_end': forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
            'due_date': forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'select'}),
            'remarks': forms.Textarea(attrs={'class': 'textarea', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['invoice_number'].required = False  # Make it optional
        self.fields['transporter'].queryset = Transporter.objects.filter(is_active=True)
        self.fields['due_date'].required = False
        self.fields['remarks'].required = False

    def save(self, commit=True):
        instance = super().save(commit=False)
        if not instance.invoice_number:
            # Auto-generate invoice number: INV-YYYY-MM-TRANSPORTER_INITIALS
            transporter_initials = "".join([word[0].upper() for word in instance.transporter.name.split()[:3]])
            instance.invoice_number = f"INV-{instance.invoice_date.strftime('%Y-%m')}-{transporter_initials}"
        if commit:
            instance.save()
        return instance


class FuelRecordForm(forms.ModelForm):
    class Meta:
        model = FuelRecord
        fields = [
            'trip', 'date', 'fuel_type', 'litres', 'cost_per_litre',
            'total_cost', 'fuel_station', 'odometer_reading', 'receipt_number', 'remarks'
        ]
        widgets = {
            'trip': forms.Select(attrs={'class': 'select'}),
            'date': forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
            'fuel_type': forms.Select(attrs={'class': 'select'}),
            'litres': forms.NumberInput(attrs={'class': 'input', 'step': '0.01', 'min': '0.01'}),
            'cost_per_litre': forms.NumberInput(attrs={'class': 'input', 'step': '0.01', 'min': '0.01'}),
            'total_cost': forms.NumberInput(attrs={'class': 'input', 'step': '0.01', 'readonly': True}),
            'fuel_station': forms.TextInput(attrs={'class': 'input'}),
            'odometer_reading': forms.NumberInput(attrs={'class': 'input', 'min': '0'}),
            'receipt_number': forms.TextInput(attrs={'class': 'input'}),
            'remarks': forms.Textarea(attrs={'class': 'textarea', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['trip'].queryset = Trip.objects.select_related('truck', 'transporter').order_by('-created_at')

        optional_fields = ['fuel_station', 'odometer_reading', 'receipt_number', 'remarks']
        for field in optional_fields:
            self.fields[field].required = False

    def clean(self):
        cleaned_data = super().clean()
        litres = cleaned_data.get('litres')
        cost_per_litre = cleaned_data.get('cost_per_litre')

        if litres and cost_per_litre:
            cleaned_data['total_cost'] = litres * cost_per_litre

        return cleaned_data


# ------------------------------------------------------------------
#  PAYMENT AND CREDIT FORMS
# ------------------------------------------------------------------
# In forms.py
import logging

logger = logging.getLogger(__name__)


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = [
            'payment_date', 'amount', 'payment_method',
            'reference_number', 'remarks'
        ]
        widgets = {
            'payment_date': forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
            'amount': forms.NumberInput(attrs={'class': 'input', 'step': '0.01', 'min': '0.01'}),
            'payment_method': forms.Select(attrs={'class': 'select'}),
            'reference_number': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Transaction reference'}),
            'remarks': forms.Textarea(attrs={'class': 'textarea', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['reference_number'].required = False
        self.fields['remarks'].required = False

        # Set default payment date to today
        if not self.instance.pk:
            from django.utils import timezone
            self.fields['payment_date'].initial = timezone.now().date()


class InvoiceCreditForm(forms.ModelForm):
    class Meta:
        model = InvoiceCredit
        fields = [
            'credit_type', 'trip', 'quantity', 'amount',
            'description', 'remarks'
        ]
        widgets = {
            'credit_type': forms.Select(attrs={'class': 'select'}),
            'trip': forms.Select(attrs={'class': 'select'}),
            'quantity': forms.NumberInput(attrs={'class': 'input', 'step': '0.01', 'min': '0.01'}),
            'amount': forms.NumberInput(attrs={'class': 'input', 'step': '0.01', 'min': '0.01'}),
            'description': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Description of credit/deduction'}),
            'remarks': forms.Textarea(attrs={'class': 'textarea', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        # Extract invoice from kwargs if passed
        invoice = kwargs.pop('invoice', None)
        super().__init__(*args, **kwargs)

        # Filter trips based on the provided invoice
        if invoice:
            self.fields['trip'].queryset = Trip.objects.filter(invoice=invoice)
        else:
            self.fields['trip'].queryset = Trip.objects.none()

        self.fields['trip'].required = False
        self.fields['quantity'].required = False
        self.fields['remarks'].required = False


# ------------------------------------------------------------------
#  MASTER-TABLE FORMS (used by reusable ModelCRUD)
# ------------------------------------------------------------------
class DriverForm(forms.ModelForm):
    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
    )

    class Meta:
        model = Driver
        fields = [
            'first_name', 'last_name', 'license_number', 'phone', 'email',
            'is_active', 'remarks'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'input', 'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Last Name'}),
            'license_number': forms.TextInput(attrs={'class': 'input', 'placeholder': 'License Number'}),
            'phone': forms.TextInput(attrs={'class': 'input', 'placeholder': '+254712345678'}),
            'email': forms.EmailInput(attrs={'class': 'input', 'placeholder': 'email@example.com'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'checkbox'}),
            'remarks': forms.Textarea(attrs={'class': 'textarea', 'rows': 3, 'placeholder': 'Remarks'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        optional_fields = ['phone', 'email', 'remarks']
        for field in optional_fields:
            self.fields[field].required = False
        self.fields['phone'].validators.append(self.phone_regex)


class TruckForm(forms.ModelForm):
    class Meta:
        model = Truck
        fields = [
            'truck_number', 'make', 'model', 'year', 'truck_type',
            'capacity_tons', 'fuel_tank_capacity', 'current_driver',  # ✅ Added current_driver
            'is_active', 'remarks'
        ]
        widgets = {
            'truck_number': forms.TextInput(attrs={'class': 'input', 'placeholder': 'TRK001'}),
            'make': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Make'}),
            'model': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Model'}),
            'year': forms.NumberInput(attrs={'class': 'input', 'min': '1980', 'max': '2030'}),
            'truck_type': forms.Select(attrs={'class': 'select'}),
            'capacity_tons': forms.NumberInput(attrs={'class': 'input', 'step': '0.01', 'min': '0.01'}),
            'fuel_tank_capacity': forms.NumberInput(attrs={'class': 'input', 'step': '0.01', 'min': '0.01'}),
            'current_driver': forms.Select(attrs={'class': 'select'}),  # ✅ Added widget
            'is_active': forms.CheckboxInput(attrs={'class': 'checkbox'}),
            'remarks': forms.Textarea(attrs={'class': 'textarea', 'rows': 3, 'placeholder': 'Remarks'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ✅ Filter active drivers for current_driver
        self.fields['current_driver'].queryset = Driver.objects.filter(is_active=True)
        self.fields['current_driver'].required = False  # Optional

        optional_fields = ['make', 'model', 'year', 'capacity_tons', 'fuel_tank_capacity', 'remarks']
        for field in optional_fields:
            self.fields[field].required = False


class DestinationForm(forms.ModelForm):
    class Meta:
        model = Destination
        fields = ['name', 'region', 'country', 'coordinates', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Destination Name'}),
            'region': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Region/State'}),
            'country': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Country'}),
            'coordinates': forms.TextInput(attrs={'class': 'input', 'placeholder': 'lat,lon'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'checkbox'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['region'].required = False
        self.fields['coordinates'].required = False


class TransporterForm(forms.ModelForm):
    class Meta:
        model = Transporter
        fields = [
            'name', 'contact_person', 'phone', 'email', 'address',
            'postal_address', 'is_active', 'remarks'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Transporter Name'}),
            'contact_person': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Contact Person'}),
            'phone': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Phone'}),
            'email': forms.EmailInput(attrs={'class': 'input', 'placeholder': 'Email'}),
            'address': forms.Textarea(attrs={'class': 'textarea', 'rows': 3, 'placeholder': 'Address'}),
            'postal_address': forms.TextInput(attrs={'class': 'input', 'placeholder': 'P.O. Box'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'checkbox'}),
            'remarks': forms.Textarea(attrs={'class': 'textarea', 'rows': 3, 'placeholder': 'Remarks'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        optional_fields = ['contact_person', 'phone', 'email', 'address', 'postal_address', 'remarks']
        for field in optional_fields:
            self.fields[field].required = False


class ExpenseCategoryForm(forms.ModelForm):
    class Meta:
        model = ExpenseCategory
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Category Name'}),
            'description': forms.Textarea(attrs={'class': 'textarea', 'rows': 3, 'placeholder': 'Description'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'checkbox'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['description'].required = False


class CargoTypeForm(forms.ModelForm):
    class Meta:
        model = CargoType
        fields = ['name', 'description', 'unit_of_measure', 'is_hazardous', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Cargo Type Name'}),
            'description': forms.Textarea(attrs={'class': 'textarea', 'rows': 3, 'placeholder': 'Description'}),
            'unit_of_measure': forms.TextInput(attrs={'class': 'input', 'placeholder': 'e.g. tons, pieces'}),
            'is_hazardous': forms.CheckboxInput(attrs={'class': 'checkbox'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'checkbox'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['description'].required = False


# ------------------------------------------------------------------
#  EXPENSE FORM
# ------------------------------------------------------------------
class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = [
            'expense_level', 'trip', 'truck', 'category', 'description',
            'amount', 'date', 'receipt_number', 'vendor', 'is_recurring', 'remarks'
        ]
        widgets = {
            'expense_level': forms.Select(attrs={'class': 'select'}),
            'trip': forms.Select(attrs={'class': 'select', 'data-placeholder': 'Select trip (trip-level only)'}),
            'truck': forms.Select(attrs={'class': 'select', 'data-placeholder': 'Select truck (truck-level only)'}),
            'category': forms.Select(attrs={'class': 'select'}),
            'description': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Description'}),
            'amount': forms.NumberInput(attrs={'class': 'input', 'step': '0.01', 'min': '0.01'}),
            'date': forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
            'receipt_number': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Receipt / ref number'}),
            'vendor': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Vendor / service provider'}),
            'is_recurring': forms.CheckboxInput(attrs={'class': 'checkbox'}),
            'remarks': forms.Textarea(attrs={'class': 'textarea', 'rows': 3, 'placeholder': 'Additional notes'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Querysets for related fields
        self.fields['trip'].queryset = Trip.objects.select_related('truck').order_by('-created_at')
        self.fields['truck'].queryset = Truck.objects.filter(is_active=True).order_by('truck_number')
        self.fields['category'].queryset = ExpenseCategory.objects.filter(is_active=True).order_by('name')

        # Optional fields
        optional_fields = ['trip', 'truck', 'receipt_number', 'vendor', 'remarks']
        for field in optional_fields:
            self.fields[field].required = False

    def clean(self):
        cleaned_data = super().clean()
        level = cleaned_data.get('expense_level')
        trip = cleaned_data.get('trip')
        truck = cleaned_data.get('truck')

        if level == Expense.ExpenseLevel.TRIP and not trip:
            raise ValidationError(_("Trip must be specified for trip-level expenses."))
        if level == Expense.ExpenseLevel.TRUCK and not truck:
            raise ValidationError(_("Truck must be specified for truck-level expenses."))
        if level == Expense.ExpenseLevel.BUSINESS and (trip or truck):
            raise ValidationError(_("Business-level expenses should not be linked to trip or truck."))

        # Ensure only relevant relationship is set
        if level == Expense.ExpenseLevel.TRIP:
            cleaned_data['truck'] = None
        elif level == Expense.ExpenseLevel.TRUCK:
            cleaned_data['trip'] = None
        elif level == Expense.ExpenseLevel.BUSINESS:
            cleaned_data['trip'] = None
            cleaned_data['truck'] = None

        return cleaned_data


# ------------------------------------------------------------------
#  FILTER FORM (logistics report)
# ------------------------------------------------------------------
class LogisticsFilterForm(forms.Form):
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'input', 'type': 'date'})
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'input', 'type': 'date'})
    )
    status = forms.ChoiceField(
        required=False,
        choices=[('', 'All Statuses')] + list(Trip.TripStatus.choices),
        widget=forms.Select(attrs={'class': 'select'})
    )
    delivery_status = forms.ChoiceField(
        required=False,
        choices=[('', 'All Delivery Statuses')] + list(Trip.DeliveryStatus.choices),
        widget=forms.Select(attrs={'class': 'select'})
    )
    transporter = forms.ModelChoiceField(
        required=False,
        queryset=Transporter.objects.none(),
        empty_label='All Transporters',
        widget=forms.Select(attrs={'class': 'select'})
    )
    destination = forms.ModelChoiceField(
        required=False,
        queryset=Destination.objects.none(),
        empty_label='All Destinations',
        widget=forms.Select(attrs={'class': 'select'})
    )
    truck = forms.ModelChoiceField(
        required=False,
        queryset=Truck.objects.none(),
        empty_label='All Trucks',
        widget=forms.Select(attrs={'class': 'select'})
    )
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input',
            'placeholder': 'Search trucks, transporters, destinations...'
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Use active managers for filters
        self.fields['transporter'].queryset = Transporter.objects.filter(is_active=True)
        self.fields['destination'].queryset = Destination.objects.filter(is_active=True)
        self.fields['truck'].queryset = Truck.objects.filter(is_active=True)


class AnalyticsFilterForm(forms.Form):
    """Main analytics dashboard filter form"""
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'input'
        }),
        required=True,
        initial=lambda: timezone.now().date() - timedelta(days=30)
    )

    end_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'input'
        }),
        required=True,
        initial=timezone.now().date
    )


class TruckComparisonForm(forms.Form):
    """Form for comparing multiple trucks"""
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'input'
        }),
        required=True,
        initial=lambda: timezone.now().date() - timedelta(days=30)
    )

    end_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'input'
        }),
        required=True,
        initial=timezone.now().date
    )

    trucks = forms.ModelMultipleChoiceField(
        queryset=Truck.objects.filter(is_active=True).order_by('truck_number'),
        widget=forms.SelectMultiple(attrs={
            'class': 'select is-multiple',
            'size': '8'
        }),
        required=True,
        help_text="Select 2-6 trucks for comparison (hold Ctrl/Cmd for multiple)"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add truck display with make/model in choices
        truck_choices = []
        for truck in Truck.objects.filter(is_active=True).order_by('truck_number'):
            display_name = truck.truck_number
            if truck.make:
                display_name += f" ({truck.make} {truck.model})"
            truck_choices.append((truck.id, display_name))
        self.fields['trucks'].choices = truck_choices

    def clean_trucks(self):
        trucks = self.cleaned_data['trucks']
        if len(trucks) < 2:
            raise forms.ValidationError("Please select at least 2 trucks for comparison.")
        if len(trucks) > 6:
            raise forms.ValidationError("Please select no more than 6 trucks for comparison.")
        return trucks


class TripProfitabilityFilterForm(forms.Form):
    """Form for filtering trip profitability analysis"""
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'input'
        }),
        required=True,
        initial=lambda: timezone.now().date() - timedelta(days=30)
    )

    end_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'input'
        }),
        required=True,
        initial=timezone.now().date
    )

    truck = forms.ModelChoiceField(
        queryset=Truck.objects.filter(is_active=True).order_by('truck_number'),
        widget=forms.Select(attrs={'class': 'select'}),
        required=False,
        empty_label="All Trucks"
    )

    transporter = forms.ModelChoiceField(
        queryset=Transporter.objects.filter(is_active=True).order_by('name'),
        widget=forms.Select(attrs={'class': 'select'}),
        required=False,
        empty_label="All Transporters"
    )

    destination = forms.ModelChoiceField(
        queryset=Destination.objects.filter(is_active=True).order_by('name'),
        widget=forms.Select(attrs={'class': 'select'}),
        required=False,
        empty_label="All Destinations"
    )

    min_margin = forms.DecimalField(
        widget=forms.NumberInput(attrs={
            'class': 'input',
            'placeholder': 'e.g., 10.0',
            'step': '0.1'
        }),
        required=False,
        help_text="Minimum profit margin percentage"
    )

    sort_by = forms.ChoiceField(
        choices=[
            ('margin_desc', 'Highest Margin First'),
            ('margin_asc', 'Lowest Margin First'),
            ('profit_desc', 'Highest Profit First'),
            ('profit_asc', 'Lowest Profit First'),
            ('revenue_desc', 'Highest Revenue First'),
            ('date_desc', 'Most Recent First'),
        ],
        widget=forms.Select(attrs={'class': 'select'}),
        initial='margin_desc',
        required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Custom display for truck choices
        truck_choices = [('', 'All Trucks')]
        for truck in Truck.objects.filter(is_active=True).order_by('truck_number'):
            display_name = truck.truck_number
            if truck.make:
                display_name += f" ({truck.make} {truck.model})"
            truck_choices.append((truck.id, display_name))
        self.fields['truck'].choices = truck_choices


class BusinessMetricsForm(forms.Form):
    """Form for business-level metrics and comparisons"""
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'input'
        }),
        required=True
    )

    end_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'input'
        }),
        required=True
    )

    compare_with_previous = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={'class': 'checkbox'}),
        required=False,
        initial=True,
        help_text="Compare with previous period of same length"
    )

    group_by = forms.ChoiceField(
        choices=[
            ('week', 'Weekly'),
            ('month', 'Monthly'),
            ('quarter', 'Quarterly'),
        ],
        widget=forms.Select(attrs={'class': 'select'}),
        initial='week',
        required=False,
        help_text="Group results by time period"
    )

    include_expenses = forms.MultipleChoiceField(
        choices=[
            ('fuel', 'Fuel Costs'),
            ('maintenance', 'Maintenance'),
            ('insurance', 'Insurance'),
            ('permits', 'Permits & Licenses'),
            ('trip_expenses', 'Trip-level Expenses'),
            ('business_expenses', 'Business Expenses'),
        ],
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        initial=['fuel', 'trip_expenses', 'business_expenses']
    )

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date:
            if start_date >= end_date:
                raise forms.ValidationError("End date must be after start date.")

            # Warn if date range is too large
            if (end_date - start_date).days > 365:
                raise forms.ValidationError("Date range cannot exceed 1 year.")

        return cleaned_data


class ExpenseCategoryAnalysisForm(forms.Form):
    """Form for analyzing expenses by category"""
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'input'
        }),
        required=True
    )

    end_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'input'
        }),
        required=True
    )

    expense_level = forms.ChoiceField(
        choices=[
            ('', 'All Levels'),
            ('trip', 'Trip Level'),
            ('truck', 'Truck Level'),
            ('business', 'Business Level'),
        ],
        widget=forms.Select(attrs={'class': 'select'}),
        required=False
    )

    truck = forms.ModelChoiceField(
        queryset=Truck.objects.filter(is_active=True).order_by('truck_number'),
        widget=forms.Select(attrs={'class': 'select'}),
        required=False,
        empty_label="All Trucks"
    )

    view_type = forms.ChoiceField(
        choices=[
            ('summary', 'Summary View'),
            ('detailed', 'Detailed Breakdown'),
            ('trends', 'Expense Trends'),
        ],
        widget=forms.RadioSelect(),
        initial='summary',
        required=True)