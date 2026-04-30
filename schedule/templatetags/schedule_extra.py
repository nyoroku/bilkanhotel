# pos/templatetags/schedule_extras.py
from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def duration_hours(start_datetime, end_datetime):
    """Calculate duration between two datetime objects in hours and minutes."""
    if not start_datetime or not end_datetime:
        return "Unknown"

    duration = end_datetime - start_datetime
    total_minutes = int(duration.total_seconds() / 60)
    hours = total_minutes // 60
    minutes = total_minutes % 60

    if hours > 0 and minutes > 0:
        return f"{hours}h {minutes}m"
    elif hours > 0:
        return f"{hours}h"
    else:
        return f"{minutes}m"


@register.filter
def is_shift_active(shift):
    """Check if a shift is currently active."""
    now = timezone.now()
    return shift.start_datetime <= now <= shift.end_datetime


@register.filter
def is_shift_upcoming(shift):
    """Check if a shift is upcoming."""
    now = timezone.now()
    return shift.start_datetime > now


@register.filter
def shift_status(shift):
    """Get the status of a shift."""
    now = timezone.now()
    if shift.start_datetime > now:
        return 'upcoming'
    elif shift.end_datetime > now:
        return 'active'
    else:
        return 'past'


@register.filter
def get_item(dictionary, key):
    """
    Template filter to get dictionary value by key.
    Usage: {{ my_dict|get_item:my_key }}
    """
    if dictionary is None:
        return None
    return dictionary.get(key)

