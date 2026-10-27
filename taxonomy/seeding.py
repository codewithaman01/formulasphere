"""Reads the plain-text data files and fills the taxonomy tables (levels, grades, subjects).

Everything is data, not code: to add a grade, subject or level, add a line to a file in
formulas/data/ (or add it in the panel). Loading only creates what is missing; it never changes
a row you have already edited.

File format: one record per line, fields separated by |, lines starting with # are comments.
"""
from pathlib import Path
from django.utils.text import slugify
from .models import AcademicLevel, Grade, Subject

DEFAULT_DIR = Path(__file__).resolve().parents[1] / "formulas" / "data"


def read_rows(path, minimum=1):
    """Yield (line number, [fields]) for each data line of a file."""
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = [x.strip() for x in line.split("|")]
        if len(parts) < minimum:
            raise ValueError(f"{Path(path).name} line {n}: expected at least {minimum} fields, found {len(parts)}")
        yield n, parts


def data_dir(custom=None):
    return Path(custom) if custom else DEFAULT_DIR


def load_levels(folder=None):
    made = 0
    for _, p in read_rows(data_dir(folder) / "levels.txt", 3):
        slug, name, order = p[0], p[1], int(p[2])
        _, new = AcademicLevel.objects.get_or_create(
            slug=slug, defaults={"name": name, "sort_order": order, "description": p[3] if len(p) > 3 else ""})
        made += new
    return made


def grade_codes(folder=None):
    """{'S9': row, ...}: the short codes used in the formula files, from grades.txt."""
    out = {}
    for _, p in read_rows(data_dir(folder) / "grades.txt", 8):
        out[p[0]] = {"slug": p[1], "name": p[2], "level": p[3], "number": int(p[4]) if p[4] else None,
                     "tier": p[5], "difficulty": p[6], "order": int(p[7])}
    return out


def load_grades(folder=None):
    made = 0
    for code, g in grade_codes(folder).items():
        level = AcademicLevel.objects.get(slug=g["level"])
        _, new = Grade.objects.get_or_create(slug=g["slug"], defaults={
            "name": g["name"], "level": level, "number": g["number"], "default_tier": g["tier"],
            "default_difficulty": g["difficulty"], "sort_order": g["order"]})
        made += new
    return made


def subject_codes(folder=None):
    """{'M': {'name':..., 'description':..., 'icon':...}}: the subject codes used in the data files."""
    out = {}
    for _, p in read_rows(data_dir(folder) / "subjects.txt", 2):
        out[p[0]] = {"name": p[1], "description": p[2] if len(p) > 2 and p[2] else f"{p[1]} formulas and concepts.",
                     "icon": p[3] if len(p) > 3 and p[3] else slugify(p[1])}
    return out


def load_subjects(folder=None):
    made = 0
    for i, (code, s) in enumerate(subject_codes(folder).items()):
        _, new = Subject.objects.get_or_create(slug=slugify(s["name"]), defaults={
            "name": s["name"], "description": s["description"], "is_published": True,
            "icon": s["icon"], "sort_order": i})
        made += new
    return made
