from .models import AuditLog


def log(actor, action, target="", detail=""):
    """Record one access-related event. actor may be None (for example a lock-out)."""
    AuditLog.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        actor_name=getattr(actor, "username", "") or "",
        action=action, target=str(target)[:200], detail=str(detail)[:300])
