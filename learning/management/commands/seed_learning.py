from pathlib import Path
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from learning.models import Course, TuitionOffer
from taxonomy.models import Grade, Subject, Topic
from taxonomy.seeding import read_rows, subject_codes

DATA = Path(__file__).resolve().parents[2] / "data"


def _subject(code, codes):
    return Subject.objects.filter(slug=slugify(codes[code]["name"])).first()


class Command(BaseCommand):
    help = ("Create starter courses and tuition offers from learning/data/courses.txt and tuition.txt. They are created as "
            "unpublished drafts (use --publish to publish them). Safe to run again; existing rows are never changed.")

    def add_arguments(self, parser):
        parser.add_argument("--dir", default=str(DATA), help="Folder holding your own courses.txt and tuition.txt")
        parser.add_argument("--publish", action="store_true", help="Create new rows as published")

    def handle(self, *a, **o):
        folder, codes = Path(o["dir"]), subject_codes()
        grades = {g.slug: g for g in Grade.objects.all()}
        made_c = made_t = 0
        for n, p in read_rows(folder / "courses.txt", 9):
            sub = _subject(p[2], codes)
            if sub is None:
                self.stderr.write(f"courses.txt line {n}: subject '{p[2]}' not found. Run seed_content first.")
                continue
            c, new = Course.objects.get_or_create(slug=p[0], defaults=dict(
                title=p[1], subject=sub, mode=p[4], duration_weeks=int(p[5]) if p[5] else None, price=p[6] or 0, summary=p[7],
                syllabus="\n".join(x.strip() for x in (p[9] if len(p) > 9 else "").split("//") if x.strip()),
                description=p[10] if len(p) > 10 else "", is_published=o["publish"]))
            if new:
                made_c += 1
                c.grades.set([grades[g] for g in p[3].split(";") if g in grades])
                c.topics.set(Topic.objects.filter(subject=sub, name__in=[t for t in p[8].split(";") if t]))
        for n, p in read_rows(folder / "tuition.txt", 8):
            sub = _subject(p[2], codes)
            if sub is None:
                self.stderr.write(f"tuition.txt line {n}: subject '{p[2]}' not found. Run seed_content first.")
                continue
            t, new = TuitionOffer.objects.get_or_create(slug=p[0], defaults=dict(
                title=p[1], subject=sub, mode=p[4], area=p[5], fee_note=p[6], group_size=int(p[7]) if p[7] else None,
                description=p[8] if len(p) > 8 else "", is_published=o["publish"]))
            if new:
                made_t += 1
                t.grades.set([grades[g] for g in p[3].split(";") if g in grades])
        state = "published" if o["publish"] else "as drafts. Review them in the panel, then tick Published"
        self.stdout.write(f"{made_c} courses and {made_t} tuition offers created {state}.")
