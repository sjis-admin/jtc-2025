from django import template
from decimal import Decimal

register = template.Library()

@register.filter
def format_price(event):
    """
    Formats the price display for an event.
    - If both individual and team fees exist: "৳100 / ৳200"
    - If only one exists: "৳100"
    - If fees are the same, shows one: "৳100"
    - If none exist: "Free"
    """
    individual_fee = getattr(event, 'individual_fee', None)
    team_fee = getattr(event, 'team_fee', None)

    # Ensure fees are decimals for comparison
    if individual_fee is not None:
        individual_fee = Decimal(individual_fee)
    if team_fee is not None:
        team_fee = Decimal(team_fee)

    if individual_fee is not None and team_fee is not None:
        # If fees are the same, show only one
        if individual_fee == team_fee:
            return f"৳{individual_fee:,.0f}"
        return f"৳{individual_fee:,.0f} / ৳{team_fee:,.0f}"
    elif individual_fee is not None:
        return f"৳{individual_fee:,.0f}"
    elif team_fee is not None:
        return f"৳{team_fee:,.0f}"
    
    # Fallback for min_fee if the annotations are not present from the view
    min_fee = getattr(event, 'min_fee', None)
    if min_fee is not None and Decimal(min_fee) > 0:
        return f"৳{Decimal(min_fee):,.0f}"
    elif min_fee is not None and Decimal(min_fee) == 0:
        return "Free"

    return "N/A"
