# registration/templatetags/math_filters.py
from django import template
from decimal import Decimal

register = template.Library()

@register.filter
def div(value, divisor):
    """
    Divides the value by the divisor.
    Usage: {{ value|div:divisor }}
    """
    try:
        if not divisor or divisor == 0:
            return 0
        return float(value) / float(divisor)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0

@register.filter
def mul(value, multiplier):
    """
    Multiplies the value by the multiplier.
    Usage: {{ value|mul:multiplier }}
    """
    try:
        if not value or not multiplier:
            return 0
        return float(value) * float(multiplier)
    except (ValueError, TypeError):
        return 0

@register.filter
def sub(value, subtrahend):
    """
    Subtracts the subtrahend from the value.
    Usage: {{ value|sub:subtrahend }}
    """
    try:
        if value is None:
            value = 0
        if subtrahend is None:
            subtrahend = 0
        return float(value) - float(subtrahend)
    except (ValueError, TypeError):
        return 0

@register.filter
def percentage(value, total):
    """
    Calculates percentage of value in total.
    Usage: {{ value|percentage:total }}
    """
    try:
        if not total or total == 0:
            return 0
        if not value:
            value = 0
        return round((float(value) / float(total)) * 100, 1)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0

@register.filter
def format_currency(value):
    """
    Formats a number as currency with ৳ symbol.
    Usage: {{ value|format_currency }}
    """
    try:
        if not value:
            return "৳0"
        return f"৳{float(value):,.0f}"
    except (ValueError, TypeError):
        return "৳0"

@register.filter 
def add(value, arg):
    """
    Adds the arg to the value.
    Usage: {{ value|add:arg }}
    """
    try:
        if value is None:
            value = 0
        if arg is None:
            arg = 0
        return float(value) + float(arg)
    except (ValueError, TypeError):
        return 0