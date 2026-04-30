# pos/templatetags/math_filters.py
from django import template

register = template.Library()

@register.filter
def sub(value, arg):
    """Subtract arg from value"""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def sum_list(value):
    """
    Sum the 'subtotal' field from OrderItem objects.
    """
    if not value:
        return 0

    try:
        return sum(float(item.subtotal) for item in value if item.subtotal is not None)
    except Exception as e:
        from django.conf import settings
        if settings.DEBUG:
            print(f"sum_list error: {e}")
        return 0

