"""Stops password and code guessing: after LIMIT failures the attempt is refused for WINDOW seconds.
Uses Django's cache. The default in-memory cache is per process; in production configure a shared
cache (database, Redis or Memcached) in CACHES so the count is shared between workers."""
from django.conf import settings
from django.core.cache import cache

# Set in config/settings.py (FS_LOCKOUT_LIMIT, FS_LOCKOUT_IP_LIMIT, FS_LOCKOUT_MINUTES in .env).
LIMIT = getattr(settings, "LOCKOUT_LIMIT", 5)
IP_LIMIT = getattr(settings, "LOCKOUT_IP_LIMIT", 30)
WINDOW = getattr(settings, "LOCKOUT_MINUTES", 15) * 60


def _key(kind, ident):
    return f"fs-lock:{kind}:{ident}"


def is_locked(kind, ident, limit=LIMIT):
    return cache.get(_key(kind, ident), 0) >= limit


def fail(kind, ident):
    k = _key(kind, ident)
    cache.add(k, 0, WINDOW)
    try:
        return cache.incr(k)
    except ValueError:
        cache.set(k, 1, WINDOW)
        return 1


def clear(kind, ident):
    cache.delete(_key(kind, ident))


def ip_of(request):
    # Behind a proxy this is the proxy's address; configure the proxy to pass the real one if needed.
    return request.META.get("REMOTE_ADDR", "?")


def login_blocked(request, username):
    ip = ip_of(request)
    return is_locked("login", f"{username.lower()}|{ip}") or is_locked("loginip", ip, IP_LIMIT)


def login_failed(request, username):
    ip = ip_of(request)
    n = fail("login", f"{username.lower()}|{ip}")
    fail("loginip", ip)
    if n == LIMIT:
        from .audit import log
        log(None, "login.locked", username, f"{LIMIT} failed sign-ins from {ip}")


def login_ok(request, username):
    clear("login", f"{username.lower()}|{ip_of(request)}")
