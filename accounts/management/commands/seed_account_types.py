from pathlib import Path
from django.core.management.base import BaseCommand
from accounts.models import AccountType, Profile
from taxonomy.models import Grade
from taxonomy.seeding import read_rows

DEFAULT_FILE = Path(__file__).resolve().parents[2] / "data" / "account_types.txt"


class Command(BaseCommand):
    help = ("Create the account types listed in accounts/data/account_types.txt if missing (Student, Teacher, Professor, "
            "Research Scholar...), and mark existing users without a type as the default type. Safe to run again. "
            "Edit or add types any time in /panel/c/account_types/ or in that file.")

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(DEFAULT_FILE), help="Your own list, same format")
        parser.add_argument("--default", default=None, help="Slug of the type for existing users without one "
                            "(default: FS_DEFAULT_ACCOUNT_TYPE, normally 'student')")

    def handle(self, *a, **o):
        from django.conf import settings
        known = set(Grade.objects.values_list("slug", flat=True))
        for i, (n, p) in enumerate(read_rows(o["file"], 5)):
            slug, name, asks, main, every = p[0], p[1], p[2] == "1", p[3], p[4] == "1"
            extra = [g for g in (p[5].split(",") if len(p) > 5 else []) if g.strip()]
            for g in ([main] if main else []) + extra:
                if g not in known:
                    self.stderr.write(f"line {n}: grade '{g}' does not exist yet. Run seed_content first (or add it under Grades).")
            AccountType.objects.get_or_create(slug=slug, defaults=dict(
                name=name, asks_grade=asks, default_grade=main, all_grades=every,
                allowed_grades=[g.strip() for g in extra], description=p[6] if len(p) > 6 else "", sort_order=i))
        default = AccountType.objects.filter(slug=o["default"] or settings.DEFAULT_ACCOUNT_TYPE).first()
        moved = Profile.objects.filter(account_type__isnull=True).update(account_type=default) if default else 0
        self.stdout.write(f"Account types ready. {moved} existing user(s) marked as {default.name if default else '(no default type found)'}.")
