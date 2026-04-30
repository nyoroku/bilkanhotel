from django.contrib import admin
from import_export import resources, fields
from import_export.admin import ImportExportModelAdmin
from import_export.widgets import ForeignKeyWidget
from unfold.admin import ModelAdmin as UnfoldModelAdmin
from import_export.admin import ImportExportModelAdmin as UnfoldImportExportModelAdmin
from .models import (
    Customer, Sale, LoyaltySettings, Coupon, Category, MenuItem,
    PurchaseOrderItem, PurchaseOrder, DeliveryItem, Delivery,  Order, OrderItem, WaiterRewardSettings
)


# -------------------------
# Category Import Resource
# -------------------------
class CategoryResource(resources.ModelResource):
    class Meta:
        model = Category
        actions = ['delete_selected']
        import_id_fields = ['name']
        fields = ['name', 'module']


# -------------------------
# Category Admin
# -------------------------
@admin.register(Category)
class CategoryAdmin(UnfoldImportExportModelAdmin):
    resource_class = CategoryResource
    list_display = ['name', 'module']
    search_fields = ['name']
    list_filter = ['module']
    actions = ['delete_selected']  # Enable bulk delete


# -------------------------
# MenuItem Import Resource
# -------------------------
class MenuItemResource(resources.ModelResource):
    category = fields.Field(
        column_name='category',
        attribute='category',
        widget=ForeignKeyWidget(Category, 'name')
    )

    class Meta:
        model = MenuItem
        actions = ['delete_selected']
        import_id_fields = ['name']
        fields = (
            'name', 'unit_of_measure', 'category', 'selling_price',
            'supplier_cost_price', 'stock_quantity', 'low_stock_threshold',
            'is_recipe', 'is_sold_by_weight', 'is_active'
        )


# -------------------------
# MenuItem Admin
# -------------------------
@admin.register(MenuItem)
class MenuItemAdmin(UnfoldImportExportModelAdmin):
    resource_class = MenuItemResource
    list_display = ['name', 'category', 'selling_price', 'stock_quantity', 'is_active']
    list_filter = ['category', 'is_active']
    search_fields = ['name']
    actions = ['delete_selected']  # Enable bulk delete


# -------------------------
# Customer Admin
# -------------------------
@admin.register(Customer)
class CustomerAdmin(UnfoldModelAdmin):
    list_display = ['name']
    search_fields = ['name']
    list_filter = ['name']
    actions = ['delete_selected']  # Enable bulk delete


# -------------------------
# Sale Admin
# -------------------------
@admin.register(Sale)
class SaleAdmin(UnfoldModelAdmin):
    list_display = ['order']
    list_filter = ['order']
    actions = ['delete_selected']  # Enable bulk delete


# -------------------------
# LoyaltySettings Admin
# -------------------------
@admin.register(LoyaltySettings)
class LoyaltySettingsAdmin(UnfoldModelAdmin):
    actions = ['delete_selected']  # Enable bulk delete


@admin.register(WaiterRewardSettings)
class WaiterRewardSettingsAdmin(UnfoldModelAdmin):
    actions = ['delete_selected']  # Enable bulk delete

# -------------------------
# Coupon Admin
# -------------------------
@admin.register(Coupon)
class CouponAdmin(UnfoldModelAdmin):
    list_display = (
    'code', 'discount_type', 'value', 'valid_from', 'valid_until', 'times_used', 'max_uses', 'is_active')
    list_filter = ('is_active', 'discount_type')
    search_fields = ('code', 'description')
    actions = ['delete_selected']  # Enable bulk delete


# -------------------------
# PurchaseOrder Admin
# -------------------------
@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(UnfoldModelAdmin):
    actions = ['delete_selected']  # Enable bulk delete


# -------------------------
# PurchaseOrderItem Admin
# -------------------------
@admin.register(PurchaseOrderItem)
class PurchaseOrderItemAdmin(UnfoldModelAdmin):
    actions = ['delete_selected']  # Enable bulk delete


# -------------------------
# Delivery Admin
# -------------------------
@admin.register(Delivery)
class DeliveryAdmin(UnfoldModelAdmin):
    actions = ['delete_selected']  # Enable bulk delete


# -------------------------
# DeliveryItem Admin
# -------------------------
@admin.register(DeliveryItem)
class DeliveryItemAdmin(UnfoldModelAdmin):
    actions = ['delete_selected']  # Enable bulk delete


class OrderResource(resources.ModelResource):
    class Meta:
        model = Order
        actions = ['delete_selected']


class OrderItemResource(resources.ModelResource):
    class Meta:
        model = OrderItem
        actions = ['delete_selected']

