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

# Enhanced helper function for event icon selection
def get_event_icon(event_type, event_name=None):
    """
    Return appropriate FontAwesome icon based on event type and name
    """
    event_icons = {
        'programming': 'code',
        'hackathon': 'laptop-code',
        'web': 'paint-brush',
        'design': 'palette',
        'ai': 'robot',
        'machine learning': 'brain',
        'data science': 'chart-line',
        'mobile': 'mobile-alt',
        'game': 'gamepad',
        'cybersecurity': 'shield-alt',
        'blockchain': 'link',
        'iot': 'microchip',
        'default_individual': 'user',
        'default_team': 'users'
    }
    
    if event_name:
        event_name_lower = event_name.lower()
        for keyword, icon in event_icons.items():
            if keyword in event_name_lower:
                return icon
    
    # Fallback based on event type
    if event_type == 'TEAM':
        return event_icons['default_team']
    else:
        return event_icons['default_individual']

# Template filter for better event data handling
@register.filter
def event_icon(event):
    """
    Template filter to get appropriate icon for an event
    Usage: {{ event|event_icon }}
    """
    return get_event_icon(event.event_type, event.name)