from django.contrib import admin
from unfold.admin import ModelAdmin as UnfoldModelAdmin
from .models import Room, Booking


@admin.register(Room)
class RoomAdmin(UnfoldModelAdmin):
    list_display = ['number', 'room_type', 'price_per_night', 'status', 'floor', 'is_active']
    list_filter = ['room_type', 'status', 'floor', 'is_active']
    search_fields = ['number', 'description']
    actions = ['delete_selected']


@admin.register(Booking)
class BookingAdmin(UnfoldModelAdmin):
    list_display = ['guest_name', 'room', 'check_in', 'check_out', 'total_amount', 'amount_paid', 'payment_status', 'status']
    list_filter = ['payment_status', 'status']
    search_fields = ['guest_name', 'guest_phone', 'room__number']
    actions = ['delete_selected']


