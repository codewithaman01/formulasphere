from pathlib import Path
from django.core.management.base import BaseCommand
from accounts.models import StaffRole
from accounts.permissions import ALL_CODES
from taxonomy.models import Grade
from taxonomy.seeding import read_rows

DEFAULT_FILE = Path(__file__).resolve().parents[2] / "data" / "roles.txt"


def expand_codes(text):
    """'subjects.*,formulas.review' -> every code. 'area.*' means add, change, delete and view."""
    out = []
    for c in (x.strip() for x in text.split(",") if x.strip()):
        if c.endswith(".*"):
            out += sorted(k for k in ALL_CODES if k.startswith(c[:-1]))
        else:
            out.append(c)
    return out


class Command(BaseCommand):
    help = ("Create the starter roles listed in accounts/data/roles.txt. They are only examples: add, edit or delete "
            "roles in /panel/roles/.")

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(DEFAULT_FILE), help="Your own list, same format")

    def handle(self, *a, **o):
        known = set(Grade.objects.values_list("slug", flat=True))
        for n, p in read_rows(o["file"], 3):
            codes = expand_codes(p[2])
            bad = [c for c in codes if c not in ALL_CODES]
            if bad:
                self.stderr.write(f"line {n}: unknown access code(s) {', '.join(bad)} (role '{p[0]}' skipped)")
                continue
            grades = p[3] if len(p) > 3 else ""
            every = grades.strip() == "*"
            slugs = [] if every else [g.strip() for g in grades.split(",") if g.strip()]
            for g in slugs:
                if g not in known:
                    self.stderr.write(f"line {n}: grade '{g}' does not exist yet. Run seed_content first.")
            StaffRole.objects.get_or_create(name=p[0], defaults=dict(
                description=p[1], access=sorted(set(codes)), all_grades=every, grades=slugs))
        self.stdout.write("Starter roles ready. Manage them at /panel/roles/")
