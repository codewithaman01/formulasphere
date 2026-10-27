"""Plain-text emails. Every function swallows mail errors: a broken mail server must never break sign-up or payment."""
import logging
from django.conf import settings
from django.core.mail import send_mail

log = logging.getLogger(__name__)


def _send(user, subject, body):
    if not getattr(user, "email", ""):
        return False
    try:
        send_mail(subject, body + f"\n\n-- FormulaSphere\n{settings.SITE_URL}/", settings.DEFAULT_FROM_EMAIL,
                  [user.email], fail_silently=False)
        return True
    except Exception:                      # noqa: BLE001
        log.exception("Could not send email to user %s", user.pk)
        return False


def send_welcome(user, profile):
    return _send(user, "Welcome to FormulaSphere",
                 f"Hi {user.username},\n\nYour account is ready. Your {settings.TRIAL_DAYS}-day free trial ends on "
                 f"{profile.trial_ends_at:%d %b %Y}. Basic formulas for your grade are open until then.\n\n"
                 f"Start exploring: {settings.SITE_URL}/explore/")


def send_trial_reminder(user, profile):
    return _send(user, "Your FormulaSphere trial ends soon",
                 f"Hi {user.username},\n\nYour free trial ends on {profile.trial_ends_at:%d %b %Y}. "
                 f"Choose a Premium plan to keep every formula for your grade open:\n{settings.SITE_URL}/premium/")


def send_premium_reminder(user, profile):
    return _send(user, "Your FormulaSphere Premium ends soon",
                 f"Hi {user.username},\n\nYour Premium ends on {profile.premium_until:%d %b %Y}. "
                 f"You can add another plan any time and the days are added to what you have left:\n{settings.SITE_URL}/premium/")


def send_payment_confirmed(plan_request, profile):
    return _send(plan_request.user, "Payment received - Premium is active",
                 f"Hi {plan_request.user.username},\n\nThank you. We received your payment for {plan_request.plan.name}. "
                 f"Premium is active until {profile.premium_until:%d %b %Y}.")
