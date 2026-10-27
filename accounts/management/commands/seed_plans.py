from pathlib import Path
from django.core.management.base import BaseCommand
from accounts.models import PremiumPlan
from taxonomy.seeding import read_rows

DEFAULT_FILE = Path(__file__).resolve().parents[2] / "data" / "plans.txt"


class Command(BaseCommand):
    help = ("Create starter Premium plans from accounts/data/plans.txt. The amounts are EXAMPLES, so plans are created hidden "
            "(use --show to show them). Existing plans are never changed. Edit plans any time in /panel/c/plans/.")

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(DEFAULT_FILE), help="Your own list, same format")
        parser.add_argument("--show", action="store_true", help="Create new plans as visible")

    def handle(self, *a, **o):
        made = 0
        for i, (n, p) in enumerate(read_rows(o["file"], 8)):
            _, new = PremiumPlan.objects.get_or_create(slug=p[0], defaults=dict(
                name=p[1], price=p[2], original_price=p[3] or None, duration_days=int(p[4]), tagline=p[5],
                is_featured=p[6] == "1", features="\n".join(x.strip() for x in p[7].split("//") if x.strip()),
                description=p[8] if len(p) > 8 else "", is_active=o["show"], sort_order=i))
            made += new
        self.stdout.write(f"{made} plan(s) created {'and shown' if o['show'] else 'hidden. Set your own amounts, then tick Show on the Premium page'}.")
