from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = "Load the formulas from formulas/data/formulas/*.txt (same as: seed_content --only formulas)."

    def add_arguments(self, parser):
        parser.add_argument("--draft", action="store_true", help="Load as drafts instead of published")
        parser.add_argument("--dir", help="Folder with your own data files")

    def handle(self, *a, **o):
        call_command("seed_content", only=["formulas"], draft=o["draft"], dir=o["dir"], stdout=self.stdout, stderr=self.stderr)
