from django.conf import settings
from accounts.scope import is_panel_user
from .models import Leader, SiteSetting, StaticPage

PROTECTED_PREFIXES = ("/formulas/", "/subjects/", "/explore/", "/saved/", "/history/", "/practice/")   # pages whose content is protected


def site_context(request):
    """Values every page may need, taken from settings or the database so nothing is typed into templates."""
    branding = SiteSetting.current()
    logo = branding.logo_url if branding else ""
    favicon = (branding.favicon_url if branding else "") or logo
    u = request.user
    protect = (getattr(settings, "PROTECT_CONTENT", True) and request.path.startswith(PROTECTED_PREFIXES)
               and not (u.is_authenticated and (u.is_superuser or is_panel_user(u))))   # staff must be able to copy
    return {
        "protect_content": protect,
        "footer_pages": StaticPage.objects.filter(is_published=True, show_in_footer=True),
        "site_logo_url": logo,          # blank means: use the built-in logo
        "site_favicon_url": favicon,
        "trial_days": settings.TRIAL_DAYS,
        "grant_days": settings.PREMIUM_GRANT_DAYS,
        "currency": settings.CURRENCY_SYMBOL,
        # people shown at the bottom of every page; only read if a template uses it
        "leaders": Leader.objects.filter(is_shown=True).prefetch_related("items"),
    }
