from .models import SiteLogo

def site_logo(request):
    logo = SiteLogo.objects.filter(is_active=True).first()
    return {'site_logo': logo}
