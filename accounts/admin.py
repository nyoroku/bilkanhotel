from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from .models import User
from .forms import UserAdminCreationForm, UserAdminChangeForm
from unfold.admin import ModelAdmin as UnfoldModelAdmin
from unfold.forms import AdminPasswordChangeForm

# Unregister default auth admins (only if they're registered)
try:
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass

try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass


@admin.register(User)
class CustomUserAdmin(BaseUserAdmin, UnfoldModelAdmin):
    """
    User admin using Unfold styling + default UserAdmin logic.
    """
    add_form = UserAdminCreationForm
    form = UserAdminChangeForm
    change_password_form = AdminPasswordChangeForm
    model = User
    list_display = ('email', 'first_name', 'last_name', 'role', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_active', 'groups')
    search_fields = ('email', 'first_name', 'last_name', 'employee_id')
    ordering = ('email',)

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'phone_number', 'profile_image')}),
        ('Permissions', {
            'fields': (
                'role', 'employee_id',
                'is_active', 'is_staff', 'is_superuser',
                'groups', 'user_permissions'
            ),
        }),
        ('Important Dates', {'fields': ('last_login', 'date_joined')}),
        ('POS PIN (Optional)', {'fields': ('pin',)}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'first_name', 'last_name', 'email', 'role',
                'password1', 'password2', 'pin'
            ),
        }),
    )


@admin.register(Group)
class CustomGroupAdmin(UnfoldModelAdmin):
    """Group admin with Unfold styling only."""
    list_display = ('name',)
    search_fields = ('name',)