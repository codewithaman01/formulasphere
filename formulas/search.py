"""Formula search. Works on any database (no PostgreSQL full-text search needed).

Every word you type must appear somewhere in the title, keywords, short explanation or plain-text form.
Results are ranked by where the words were found: title and keywords first, then the short explanation,
then the plain-text form. (If you later want typo-tolerant search, add an Atlas Search index and query it here.)
"""
import re
from django.db.models import Case, IntegerField, Q, Value, When
from .models import Formula, Status

# (field, weight): a word found in a higher-weight field ranks the formula higher.
FIELDS = (("title", 10), ("keywords", 10), ("short_explanation", 4), ("plain_text", 2))


def published():
    return Formula.objects.filter(status=Status.PUBLISHED)


def _words(q):
    return [w for w in re.split(r"\s+", (q or "").strip()) if w][:8]


def search_formulas(q="", subject=None, level=None, difficulty=None, topic=None, sort="relevance"):
    qs = published()
    if subject:
        qs = qs.filter(subjects__slug=subject)
    if level:
        qs = qs.filter(levels__slug=level)
    if topic:
        qs = qs.filter(topics__slug=topic)
    if difficulty:
        qs = qs.filter(difficulty=difficulty)
    words = _words(q)
    for w in words:
        cond = Q()
        for field, _ in FIELDS:
            cond |= Q(**{f"{field}__icontains": w})
        qs = qs.filter(cond)
    if words:
        score = Value(0, output_field=IntegerField())
        for w in words:
            for field, weight in FIELDS:
                score = score + Case(When(**{f"{field}__icontains": w}, then=Value(weight)),
                                     default=Value(0), output_field=IntegerField())
        qs = qs.annotate(rank=score)
    if sort == "title" or (sort == "relevance" and not words):
        qs = qs.order_by("title")
    elif sort == "recent":
        qs = qs.order_by("-updated_at")
    elif words:
        qs = qs.order_by("-rank", "title")
    return qs
