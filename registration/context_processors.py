# registration/context_processors.py
from .models import SiteLogo

def site_logo(request):
    """Context processor to make site logo available in all templates"""
    logo = SiteLogo.objects.filter(is_active=True).first()
    return {'site_logo': logo}
