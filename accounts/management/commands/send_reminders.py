"""Emails people whose trial or Premium ends soon. Run once a day (cron / Task Scheduler):
    python manage.py send_reminders
Each person is emailed once per trial and once per Premium end date."""
from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import F
from django.utils import timezone
from accounts import emails
from accounts.models import Profile


class Command(BaseCommand):
    help = "Send trial-ending and Premium-ending reminder emails."

    def handle(self, *args, **opts):
        now = timezone.now()
        sent = 0
        trial = (Profile.objects.filter(trial_ends_at__gt=now, trial_ends_at__lte=now + timedelta(days=settings.REMINDER_TRIAL_DAYS),
                                        trial_reminded_at__isnull=True)
                 .exclude(premium_until__gt=now).select_related("user"))
        for p in trial:
            if emails.send_trial_reminder(p.user, p):
                Profile.objects.filter(pk=p.pk).update(trial_reminded_at=now)
                sent += 1
        prem = (Profile.objects.filter(premium_until__gt=now, premium_until__lte=now + timedelta(days=settings.REMINDER_PREMIUM_DAYS))
                .exclude(premium_reminded_for=F("premium_until")).select_related("user"))
        for p in prem:
            if emails.send_premium_reminder(p.user, p):
                Profile.objects.filter(pk=p.pk).update(premium_reminded_for=p.premium_until)
                sent += 1
        self.stdout.write(self.style.SUCCESS(f"{sent} reminder email(s) sent."))
