from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = ("Kept so old instructions still work. Loads everything from the data files, exactly like seed_content. "
            "Loaded formulas are flagged is_demo=True because they are not expert reviewed.")

    def handle(self, *a, **o):
        call_command("seed_content", stdout=self.stdout, stderr=self.stderr)
