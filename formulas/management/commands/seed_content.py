from django.core.management.base import BaseCommand, CommandError
from formulas import seeding
from taxonomy import seeding as tax

STEPS = ["levels", "grades", "subjects", "formulas", "topics", "snippets", "explanations"]


class Command(BaseCommand):
    help = ("Load levels, grades, subjects, formulas, topics and code examples from the text files in "
            "formulas/data/. Safe to run again: it only adds what is missing and never changes rows you edited. "
            "Add content by adding lines to those files (or a new .txt file in formulas/data/formulas/).")

    def add_arguments(self, parser):
        parser.add_argument("--dir", help="Folder with your own data files (same layout as formulas/data/)")
        parser.add_argument("--only", nargs="*", choices=STEPS, help="Run only these steps")
        parser.add_argument("--draft", action="store_true", help="Load new formulas as drafts, not published")
        parser.add_argument("--check", action="store_true", help="Only check the data files for mistakes; change nothing")

    def handle(self, *a, **o):
        folder = o["dir"]
        problems = seeding.check(folder)
        for p in problems:
            self.stderr.write(p)
        if problems:
            raise CommandError(f"{len(problems)} problem(s) in the data files. Fix them and run again.")
        if o["check"]:
            n = len(seeding.parse_formulas(folder))
            self.stdout.write(f"Data files are fine: {n} formulas, {len(seeding.parse_topics(folder))} topics.")
            return
        steps = o["only"] or STEPS
        # formulas and topics need levels, grades and subjects first
        need = set(steps)
        if need & {"formulas", "topics", "snippets", "explanations"}:
            need |= {"levels", "grades", "subjects"}
        if "levels" in need or "grades" in need:
            need |= {"levels"}
        report = []
        if "levels" in need:
            report.append(f"{tax.load_levels(folder)} levels added")
        if "grades" in need:
            report.append(f"{tax.load_grades(folder)} grades added")
        if "subjects" in need:
            report.append(f"{tax.load_subjects(folder)} subjects added")
        if "formulas" in steps:
            report.append(f"{seeding.load_formulas(folder, o['draft'])} formulas added (flagged as not expert reviewed)")
        if "topics" in steps:
            linked, missing = seeding.load_topics(folder)
            report.append(f"{linked} formula-to-topic links made")
            for t in missing:
                self.stderr.write(f"topic file lists a formula that does not exist: {t}")
        if "snippets" in steps:
            report.append(f"{seeding.load_snippets(folder)} code examples loaded")
        if "explanations" in steps:
            nf, nt, ne = seeding.load_explanations(folder)
            report.append(f"{nf} formula and {nt} topic explanations and {ne} worked examples added")
        self.stdout.write("; ".join(report) + ".")
