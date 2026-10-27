"""Stops one account opening hundreds of formula pages an hour (scraping). Staff are exempt.
Uses Django's cache. The default per-process cache is fine for one server process; on a server with several
workers set CACHES to Redis or Memcached so the count is shared."""
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from accounts.scope import is_panel_user


def over_view_limit(user):
    limit = getattr(settings, "VIEW_LIMIT_PER_HOUR", 0)
    if not limit or user.is_superuser or is_panel_user(user):
        return False
    key = f"fs:views:{user.pk}:{timezone.now():%Y%m%d%H}"
    cache.add(key, 0, 3700)
    try:
        n = cache.incr(key)
    except ValueError:
        cache.set(key, 1, 3700)
        n = 1
    return n > limit
