# pos/forms.py

from django import forms
from .models import Supplier, Category, MenuItem, PurchaseOrder, \
    PurchaseOrderItem, Customer, Table, CustomerPayment, Expense, ExpenseCategory, RecipeIngredient, Order
from django.forms import inlineformset_factory


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        # Add the 'status' field to the list
        fields = ['name', 'contact_person', 'phone_number', 'supplies_to', 'status']

        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+2547...'}),
            'supplies_to': forms.Select(attrs={'class': 'form-select'}),
            # Add the widget for the new status field
            'status': forms.Select(attrs={'class': 'form-select'}),
        }


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'module']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'module': forms.Select(attrs={'class': 'form-select'}),
        }


class PurchaseOrderForm(forms.ModelForm):
    """
    Form for the main details of a Purchase Order.
    """
    # We filter the supplier queryset to only show active suppliers.
    supplier = forms.ModelChoiceField(
        queryset=Supplier.objects.filter(status=Supplier.Status.ACTIVE),
        widget=forms.Select(attrs={'class': 'select is-fullwidth'})
    )

    class Meta:
        model = PurchaseOrder
        fields = ['supplier', 'order_date', 'requested_for_section', 'notes']
        widgets = {
            'order_date': forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
            'requested_for_section': forms.Select(attrs={'class': 'select is-fullwidth'}),
            'notes': forms.Textarea(attrs={'class': 'textarea', 'rows': 3}),
        }


class PurchaseOrderItemForm(forms.ModelForm):
    """
    Form for a single line item in a Purchase Order.
    """
    # Filter the dropdown to only show items that are purchasable (not recipes).
    menu_item = forms.ModelChoiceField(
        queryset=MenuItem.objects.filter(is_recipe=False).order_by('name'),
        widget=forms.Select(attrs={'class': 'select is-fullwidth'})
    )

    class Meta:
        model = PurchaseOrderItem
        fields = ['menu_item', 'quantity_ordered']
        widgets = {
            'quantity_ordered': forms.NumberInput(attrs={'class': 'input', 'step': '0.01', 'placeholder': 'Qty'}),
        }


# This is the formset factory that will let us add multiple item rows dynamically.
PurchaseOrderItemFormSet = inlineformset_factory(
    PurchaseOrder,  # The parent model
    PurchaseOrderItem,  # The child model
    form=PurchaseOrderItemForm,  # Use our custom form for each line
    extra=1,  # Show 1 extra empty form by default
    can_delete=True,  # Allow users to delete item rows
    can_delete_extra=True
)


class OrderCreationForm(forms.ModelForm):
    class Meta:
        model = Order
        # We only need the fields that are manually selected on the form.
        # The waiter is assigned automatically, and other fields are calculated.
        fields = ['customer', 'table']

        # --- THIS IS THE KEY CHANGE ---
        # We tell Django to render the 'customer' field as a hidden input field.
        # We will control its value using our search box and JavaScript.
        widgets = {
            'customer': forms.HiddenInput(),
            'table': forms.Select(attrs={'class': 'select is-fullwidth'}),
        }


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'phone_number', 'credit_limit', 'credit_balance']   # ← add
        widgets = {
            'name': forms.TextInput(attrs={'class': 'input is-medium', 'placeholder': 'e.g., John Doe'}),
            'phone_number': forms.TextInput(attrs={'class': 'input is-medium', 'placeholder': 'e.g., 0712345678'}),
            'credit_limit': forms.NumberInput(attrs={'class': 'input is-medium'}),
            'credit_balance': forms.NumberInput(attrs={'class': 'input is-medium'}),  # ← add
        }


class TableForm(forms.ModelForm):
    class Meta:
        model = Table
        fields = ['table_number', 'is_active', 'shape']
        widgets = {
            'table_number': forms.TextInput(attrs={
                'class': 'input is-medium',
                'placeholder': 'e.g., Table 1, A5, or Patio 3'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'checkbox'}),
            'shape': forms.Select(attrs={'class': 'select is-medium'}),
        }
        labels = {
            'is_active': 'Table is active and available for seating',
            'shape': 'Table Shape',
        }


class CustomerPaymentForm(forms.ModelForm):
    class Meta:
        model = CustomerPayment
        # We only need the user to input these fields
        fields = ['customer', 'amount_paid', 'payment_method']
        widgets = {
            'customer': forms.Select(attrs={'class': 'select is-medium'}),
            'amount_paid': forms.NumberInput(attrs={'class': 'input is-medium', 'placeholder': 'Amount being paid'}),
            'payment_method': forms.Select(attrs={'class': 'select is-medium'}),
        }

    def clean_amount_paid(self):
        # Custom validation logic
        amount_paid = self.cleaned_data.get('amount_paid')
        customer = self.cleaned_data.get('customer')

        if customer and amount_paid > customer.credit_balance:
            raise forms.ValidationError(
                f"Payment amount cannot exceed the customer's credit balance of {customer.credit_balance} KES.")

        if amount_paid <= 0:
            raise forms.ValidationError("Payment amount must be a positive number.")

        return amount_paid


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['category', 'amount', 'description', 'expense_date', 'payment_method', 'receipt_image']
        widgets = {
            'category': forms.Select(attrs={'class': 'select is-medium'}),
            'amount': forms.NumberInput(attrs={'class': 'input is-medium', 'placeholder': 'Amount in KES'}),
            'description': forms.Textarea(attrs={'class': 'textarea', 'rows': 3}),
            'expense_date': forms.DateInput(attrs={'class': 'input is-medium', 'type': 'date'}),
            'payment_method': forms.Select(attrs={'class': 'select is-medium'}),
            'receipt_image': forms.ClearableFileInput(attrs={'class': 'file-input'}),
        }


class ExpenseCategoryForm(forms.ModelForm):
    class Meta:
        model = ExpenseCategory
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(
                attrs={'class': 'input is-medium', 'placeholder': 'e.g., Utilities, Rent, Salaries'}),
            'description': forms.Textarea(attrs={'class': 'textarea', 'rows': 3,
                                                 'placeholder': 'Optional description of what this category covers.'}),
        }


class MenuItemForm(forms.ModelForm):
    """
    Full model form for MenuItem with all fields and dynamic supplier filtering.
    """

    class Meta:
        model = MenuItem
        fields = [
            'name',
            'category',
            'image',
            'unit_of_measure',
            'is_recipe',
            'selling_price',
            'supplier_cost_price',
            'stock_quantity',
            'low_stock_threshold',
            'sell_by_weight',
            'is_active',
            'preferred_supplier',
            'reorder_quantity',
        ]
        widgets = {
            'unit_of_measure': forms.Select(attrs={'class': 'select is-fullwidth'}),
            'preferred_supplier': forms.Select(
                attrs={'class': 'select is-fullwidth'},
            ),
            'reorder_quantity': forms.NumberInput(
                attrs={'class': 'input', 'step': '0.01'}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # --- Dynamic supplier filtering ---
        #   1. Only ACTIVE suppliers
        #   2. Whose `supplies_to` matches the item's category.module
        qs = Supplier.objects.filter(status=Supplier.Status.ACTIVE)

        if self.instance.pk and self.instance.category_id:
            # Existing object → filter by matching category
            qs = qs.filter(supplies_to=self.instance.category.module)
        elif self.data and 'category' in self.data:
            # Creating new object but category already POSTed
            try:
                from .models import Category
                category_id = int(self.data.get('category'))
                category = Category.objects.get(pk=category_id)
                qs = qs.filter(supplies_to=category.module)
            except (ValueError, Category.DoesNotExist):
                qs = qs.none()
        else:
            # Nothing to filter on yet → empty list
            qs = qs.none()

        self.fields['preferred_supplier'].queryset = qs


# ------------------------------------------------------------------
# Inline formset for recipe ingredients
# ------------------------------------------------------------------
RecipeIngredientFormSet = inlineformset_factory(
    MenuItem,
    RecipeIngredient,
    fk_name='dish',
    fields=('ingredient', 'quantity'),
    extra=0,
    can_delete=True,
    widgets={
        'ingredient': forms.Select(attrs={'class': 'select is-fullwidth'}),
        'quantity': forms.NumberInput(attrs={'class': 'input', 'step': '0.001'}),
    }
)

