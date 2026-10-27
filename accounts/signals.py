from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.contrib.sessions.models import Session
from django.dispatch import receiver
from django.utils import timezone


@receiver(user_logged_in)
def limit_devices(sender, request, user, **kwargs):
    """Keep at most MAX_SESSIONS sign-ins per ordinary account; the oldest is signed out. Staff are exempt."""
    from .models import UserSession
    from .scope import is_panel_user
    limit = getattr(settings, "MAX_SESSIONS", 0)
    if not limit or request is None or user.is_superuser or is_panel_user(user):
        return
    key = request.session.session_key
    if not key:
        request.session.save()
        key = request.session.session_key
    UserSession.objects.get_or_create(session_key=key, defaults={"user": user})
    # forget sign-ins whose session no longer exists (expired or logged out); the one being created now stays
    live = set(Session.objects.filter(session_key__in=UserSession.objects.filter(user=user).values("session_key"),
                                      expire_date__gt=timezone.now()).values_list("session_key", flat=True)) | {key}
    UserSession.objects.filter(user=user).exclude(session_key__in=live).delete()
    rows = list(UserSession.objects.filter(user=user).order_by("created_at", "pk"))
    for old in rows[:max(len(rows) - limit, 0)]:
        if old.session_key != key:
            Session.objects.filter(session_key=old.session_key).delete()
            old.delete()
