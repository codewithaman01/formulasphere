"""Pages for signed-in people: saved formulas, history, practice, submitting formulas. Plus site pages and robots.txt."""
import re
import uuid
from datetime import timedelta

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from accounts.access import can_view, restrict_queryset
from config.prefetch import prefetch
from formulas.models import Bookmark, Example, Formula, FormulaRevision, FormulaView, PracticeAttempt, Status
from formulas.search import published
from formulas.validators import validate_latex
from formulas.workflow import snapshot
from taxonomy.models import AcademicLevel, Subject
from .models import StaticPage
from .views import _mark


# ------------------------------------------------------------------ saved formulas
@login_required
@require_POST
def bookmark_toggle(request, slug):
    f = get_object_or_404(published(), slug=slug)
    if not can_view(request.user, f):
        return redirect("pricing")
    b, created = Bookmark.objects.get_or_create(user=request.user, formula=f)
    if not created:
        b.delete()
    nxt = request.POST.get("next", "")
    return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else f"/formulas/{f.slug}/")


def _formulas_for(user, qs_ids):
    """Published formulas from a list of ids, in that order, that this person may still open."""
    rows = list(restrict_queryset(user, published().filter(pk__in=qs_ids)).distinct())
    found = {f.pk: f for f in prefetch(rows, "subjects", "levels")}
    return _mark(user, [found[i] for i in qs_ids if i in found])


@login_required
def saved(request):
    ids = list(Bookmark.objects.filter(user=request.user).values_list("formula_id", flat=True))
    return render(request, "web/saved.html", {"formulas": _formulas_for(request.user, ids)})


@login_required
def history(request):
    ids = []
    for fid in FormulaView.objects.filter(user=request.user).values_list("formula_id", flat=True)[:200]:
        if fid not in ids:
            ids.append(fid)
        if len(ids) == 30:
            break
    return render(request, "web/history.html", {"formulas": _formulas_for(request.user, ids)})


def log_view(user, formula):
    """One row per person per formula per 10 minutes, so reloading does not fill the table."""
    since = timezone.now() - timedelta(minutes=10)
    if not FormulaView.objects.filter(user=user, formula=formula, viewed_at__gte=since).exists():
        FormulaView.objects.create(user=user, formula=formula)


# ------------------------------------------------------------------ practice
def _next_example(user):
    recent = list(PracticeAttempt.objects.filter(user=user).values_list("example_id", flat=True)[:20])
    allowed = restrict_queryset(user, published())
    base = Example.objects.filter(formula__in=allowed).exclude(problem="").select_related("formula")
    for qs in (base.exclude(pk__in=recent), base):
        for ex in qs.order_by("?")[:15]:
            if can_view(user, ex.formula):
                return ex
    return None


@login_required
def practice(request):
    attempts = PracticeAttempt.objects.filter(user=request.user)
    week = attempts.filter(created_at__gte=timezone.now() - timedelta(days=7))
    stats = {"total": attempts.count(), "got": attempts.filter(got_it=True).count(),
             "week": week.count(), "week_got": week.filter(got_it=True).count()}
    stats["percent"] = round(100 * stats["got"] / stats["total"]) if stats["total"] else 0
    return render(request, "web/practice.html", {"example": _next_example(request.user), "stats": stats})


@login_required
@require_POST
def practice_answer(request, pk):
    ex = get_object_or_404(Example.objects.select_related("formula"), pk=pk, formula__status=Status.PUBLISHED)
    if can_view(request.user, ex.formula):
        PracticeAttempt.objects.create(user=request.user, example=ex, got_it=request.POST.get("got_it") == "1")
    return redirect("practice")


# ------------------------------------------------------------------ students submit formulas
class SubmissionForm(forms.ModelForm):
    class Meta:
        model = Formula
        fields = ["title", "latex", "short_explanation", "detailed_explanation", "subjects", "levels", "difficulty", "keywords"]
        labels = {"latex": "Formula in LaTeX", "short_explanation": "One-line explanation",
                  "detailed_explanation": "Longer explanation (optional)", "keywords": "Search words (optional)"}
        widgets = {"subjects": forms.CheckboxSelectMultiple, "levels": forms.CheckboxSelectMultiple,
                   "latex": forms.Textarea(attrs={"rows": 3, "spellcheck": "false", "autocomplete": "off"}),
                   "detailed_explanation": forms.Textarea(attrs={"rows": 5})}
        help_texts = {"keywords": "Words people might type, separated by commas.", "latex": ""}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["subjects"].queryset = Subject.objects.filter(is_published=True)
        self.fields["levels"].queryset = AcademicLevel.objects.all()
        self.fields["detailed_explanation"].required = False
        self.fields["keywords"].required = False

    def clean_latex(self):
        v = validate_latex(self.cleaned_data.get("latex"))
        if not v:
            raise ValidationError("Enter the formula in LaTeX.")
        return v


def _unique_slug(title):
    base = slugify(title)[:170] or "formula"
    while True:
        slug = f"{base}-{uuid.uuid4().hex[:6]}"
        if not Formula.objects.filter(slug=slug).exists():
            return slug


def _latest_note(f):
    r = f.reviews.order_by("-created_at").first()
    return r.notes if r and f.status == Status.NEEDS_CORRECTION else ""


@login_required
def submit_formula(request, pk=None):
    inst = None
    if pk:
        inst = get_object_or_404(Formula, pk=pk, created_by=request.user,
                                 status__in=[Status.DRAFT, Status.NEEDS_CORRECTION])
    elif Formula.objects.filter(created_by=request.user, created_at__gte=timezone.now() - timedelta(days=1)).count() >= settings.SUBMISSIONS_PER_DAY:
        messages.error(request, f"You can submit up to {settings.SUBMISSIONS_PER_DAY} formulas a day. Please come back tomorrow.")
        return redirect("my_submissions")
    form = SubmissionForm(request.POST or None, instance=inst)
    if request.method == "POST" and form.is_valid():
        f = form.save(commit=False)
        if inst is None:
            f.slug = _unique_slug(f.title)
            f.created_by = request.user
        f.status = Status.SUBMITTED
        f.save()
        form.save_m2m()
        last = f.revisions.first()
        FormulaRevision.objects.create(formula=f, version=(last.version + 1) if last else 1, snapshot=snapshot(f),
                                       changed_by=request.user, reason="submitted by student")
        messages.success(request, "Thank you! Your formula was sent for review. You can follow it under My submissions.")
        return redirect("my_submissions")
    return render(request, "web/submit.html", {"form": form, "editing": inst, "note": _latest_note(inst) if inst else ""})


@login_required
def my_submissions(request):
    rows = list(Formula.objects.filter(created_by=request.user).order_by("-created_at")[:50])
    for f in rows:
        f.note = _latest_note(f)
        f.can_edit = f.status in (Status.DRAFT, Status.NEEDS_CORRECTION)
    return render(request, "web/my_submissions.html", {"rows": rows})


# ------------------------------------------------------------------ site pages, robots
def static_page(request, slug):
    page = get_object_or_404(StaticPage, slug=slug, is_published=True)
    blocks = []
    for chunk in re.split(r"\n\s*\n", page.body.strip()):
        chunk = chunk.strip()
        if chunk.startswith("## "):
            head, _, rest = chunk.partition("\n")
            blocks.append(("h", head[3:].strip()))
            chunk = rest.strip()
        if chunk:
            blocks.append(("p", chunk))
    return render(request, "web/page.html", {"page": page, "blocks": blocks})


def robots(request):
    lines = ["User-agent: *", "Disallow: /panel/", "Disallow: /admin/", "Disallow: /api/", "Disallow: /formulas/",
             "Disallow: /saved/", "Disallow: /history/", "Disallow: /practice/", "Disallow: /submit/",
             f"Sitemap: {settings.SITE_URL}/sitemap.xml"]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")
