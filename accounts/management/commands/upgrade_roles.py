from django.core.management.base import BaseCommand
from accounts.models import StaffRole


class Command(BaseCommand):
    help = "One-off: convert roles made with the old three checkboxes into the new access list."

    def handle(self, *a, **kw):
        n = 0
        for r in StaffRole.objects.all():
            if r.access:
                continue
            codes = [c for flag, c in ((r.can_create, "formulas.create"), (r.can_review, "formulas.review"),
                                       (r.can_publish, "formulas.publish")) if flag]
            if codes:
                r.access = codes
                r.save(update_fields=["access"])
                n += 1
        self.stdout.write(f"Converted {n} role(s). Check them at /panel/roles/")
