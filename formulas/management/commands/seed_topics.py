from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = "Load topics, link formulas to them and load code examples (same as: seed_content --only topics snippets)."

    def add_arguments(self, parser):
        parser.add_argument("--dir", help="Folder with your own data files")

    def handle(self, *a, **o):
        call_command("seed_content", only=["topics", "snippets"], dir=o["dir"], stdout=self.stdout, stderr=self.stderr)
