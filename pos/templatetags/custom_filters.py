from django import template
from decimal import Decimal
import logging

register = template.Library()
logger = logging.getLogger(__name__)


@register.filter(name='percent_of')
def percent_of(part, whole):
    """
    Calculate percentage of part relative to whole.
    Returns 0 if invalid input or divide by zero.
    """
    try:
        # Log the raw input values for debugging
        logger.info(f"PERCENT_OF DEBUG: part={part} (type: {type(part)}), whole={whole} (type: {type(whole)})")

        # Convert to float to handle Decimal, int, float, and string inputs
        part_float = float(part) if part is not None else 0
        whole_float = float(whole) if whole is not None else 0

        logger.info(f"PERCENT_OF DEBUG: part_float={part_float}, whole_float={whole_float}")

        # Avoid division by zero
        if whole_float == 0:
            logger.warning("PERCENT_OF DEBUG: Division by zero - whole is 0")
            return 0

        # Calculate percentage
        percentage = (part_float / whole_float) * 100

        logger.info(f"PERCENT_OF DEBUG: calculated percentage={percentage}")

        # Ensure we don't return negative percentages for display
        result = max(0, percentage)
        logger.info(f"PERCENT_OF DEBUG: final result={result}")

        return result

    except (ValueError, TypeError, AttributeError) as e:
        logger.error(f"PERCENT_OF ERROR: {e} - part={part}, whole={whole}")
        return 0


@register.filter(name='safe_divide')
def safe_divide(dividend, divisor):
    """
    Safely divide two numbers, returning 0 if divisor is 0 or invalid.
    """
    try:
        dividend = float(dividend) if dividend is not None else 0
        divisor = float(divisor) if divisor is not None else 0

        if divisor == 0:
            return 0

        return dividend / divisor

    except (ValueError, TypeError, AttributeError):
        return 0


@register.filter(name='multiply')
def multiply(value, multiplier):
    """
    Multiply a value by a multiplier.
    """
    try:
        value = float(value) if value is not None else 0
        multiplier = float(multiplier) if multiplier is not None else 1

        return value * multiplier

    except (ValueError, TypeError, AttributeError):
        return 0


@register.filter(name='debug_value')
def debug_value(value):
    """
    Debug filter to see what type and value we're getting
    """
    return f"{value} (type: {type(value).__name__})"

