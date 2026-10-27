from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Count, Q
from accounts.access import can_view, get_profile, restrict_queryset
from django.conf import settings
from django.views.decorators.cache import never_cache
from formulas.models import Bookmark, Difficulty, SearchLog
from formulas.search import published, search_formulas
from taxonomy.models import AcademicLevel, Subject, Topic
import re
from django.http import HttpResponse
from django.views.decorators.http import require_GET
from config.prefetch import prefetch
from .models import Leader, LeaderItem, StoredImage
from .throttle import over_view_limit


def _mark(user, formulas):
    for f in formulas:
        f.locked = not can_view(user, f)
    return formulas


def home(request):
    featured = prefetch(list(restrict_queryset(request.user, published()).order_by("-published_at").distinct()[:6]), "subjects", "levels")
    return render(request, "web/home.html", {
        "subjects": Subject.objects.filter(is_published=True, parent=None),
        "levels": AcademicLevel.objects.all(), "featured": _mark(request.user, featured)})


def explore(request):
    g = request.GET
    qs = search_formulas(g.get("q"), g.get("subject"), g.get("level"), g.get("difficulty"), g.get("topic"), g.get("sort", "relevance"))
    qs = restrict_queryset(request.user, qs).distinct()
    page = Paginator(qs, settings.EXPLORE_PAGE_SIZE).get_page(g.get("page"))
    page.object_list = _mark(request.user, prefetch(list(page.object_list), "subjects", "levels"))
    q = (g.get("q") or "").strip()
    if q and page.number == 1:
        SearchLog.objects.create(user=request.user if request.user.is_authenticated else None, query=q[:200], result_count=page.paginator.count)
    params = g.copy(); params.pop("page", None)
    return render(request, "web/explore.html", {
        "page": page, "q": g.get("q", ""), "subjects": Subject.objects.filter(is_published=True),
        "levels": AcademicLevel.objects.all(), "qs": params.urlencode(), "filters": g,
        "difficulties": Difficulty.choices})


@never_cache
def formula_detail(request, slug):
    f = get_object_or_404(published().prefetch_related(
        "variables", "derivation_steps", "assumptions", "examples", "formula_references__reference"), slug=slug)
    prefetch([f], "subjects", "levels", "related")
    if not request.user.is_authenticated:
        return redirect(f"/login/?next={request.path}")
    if not can_view(request.user, f):
        return redirect("pricing")
    if over_view_limit(request.user):
        return render(request, "web/slow_down.html", {"limit": settings.VIEW_LIMIT_PER_HOUR}, status=429)
    from .views_user import log_view
    from accounts.scope import is_panel_user
    if not (request.user.is_superuser or is_panel_user(request.user)):
        log_view(request.user, f)
    labels = {}
    for v in f.variables.all():
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", v.symbol or ""):
            unit = re.sub(r"\\(?:mathrm|text)\{([^}]*)\}", r"\1", v.unit or "")
            labels[v.symbol] = f"{v.name} ({unit})" if unit else v.name
    return render(request, "web/formula_detail.html", {
        "f": f, "calc_labels": labels, "is_saved": Bookmark.objects.filter(user=request.user, formula=f).exists()})


def suggest(request):
    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return JsonResponse({"results": []})
    rows = restrict_queryset(request.user, published().filter(title__icontains=q)).values("title", "slug").distinct()[:6]
    return JsonResponse({"results": list(rows)})


def subject_page(request, slug):
    subject = get_object_or_404(Subject, slug=slug, is_published=True)
    topics = subject.topics.annotate(
        nf=Count("formulas", filter=Q(formulas__status="published"), distinct=True), ns=Count("snippets", distinct=True))
    return render(request, "web/subject.html", {"subject": subject, "topics": topics})


def topic_page(request, subject, slug):
    t = get_object_or_404(Topic.objects.select_related("subject"), subject__slug=subject, slug=slug)
    if not request.user.is_authenticated:
        return redirect(f"/login/?next={request.path}")
    p = get_profile(request.user)
    premium_ok = request.user.is_superuser or bool(p and p.is_premium)
    fs = prefetch(list(restrict_queryset(request.user, published().filter(topics=t)).distinct()), "subjects", "levels")
    groups = {}
    for s in t.snippets.all():
        g = groups.setdefault(s.title, {"title": s.title, "explanation": s.explanation, "items": [],
                                        "locked": s.is_premium and not premium_ok})
        g["items"].append(s)
    return render(request, "web/topic.html", {"topic": t, "formulas": _mark(request.user, fs), "groups": groups.values()})


def about(request):
    people = []
    for leader in Leader.objects.filter(is_shown=True).prefetch_related("items"):
        groups = []
        for code, _ in LeaderItem.KINDS:
            items = [i for i in leader.items.all() if i.kind == code]
            if items:
                groups.append({"heading": LeaderItem.HEADINGS[code], "items": items})
        people.append({"leader": leader, "groups": groups})
    return render(request, "web/about.html", {"people": people})


@require_GET
def db_image(request, pk):
    """Serves a picture stored in the database. Its address changes whenever the picture changes, so browsers may keep it for a year."""
    img = get_object_or_404(StoredImage, pk=pk)
    etag = f'"{img.pk}"'
    if request.headers.get("If-None-Match") == etag:
        resp = HttpResponse(status=304)
    else:
        resp = HttpResponse(bytes(img.data), content_type=img.content_type)
    resp["ETag"] = etag
    resp["Cache-Control"] = "public, max-age=31536000, immutable"
    resp["X-Content-Type-Options"] = "nosniff"
    resp["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
    return resp
