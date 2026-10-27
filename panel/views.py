"""The staff panel. Every view first asks: does one of this user's roles carry the
access code for this page? If not, 403. Nothing here knows role names."""
import json
import re
from bson import ObjectId
from datetime import timedelta
from functools import wraps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from config.prefetch import prefetch
from django_mongodb_backend import transaction
from django.db.models import Count, ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from accounts import lockout, totp
from accounts.audit import log
from accounts.models import AccountType, AuditLog, Profile, StaffAssignment, StaffRole, TOTPDevice
from accounts.permissions import SCOPED_CODES, expand, grouped, summary
from accounts.scope import (any_subject_ids, can_act, codes_for, has_access, is_panel_user, landing_url, needs_2fa,
                            pages_for, page_url, role_requires_2fa, subject_ids)
from formulas import workflow
from formulas.models import CodeSnippet, Formula, Reference, Status
from accounts.models import PlanRequest, PremiumPlan
from learning.models import Course, Enrollment, LiveClass, TuitionEnquiry, TuitionOffer
from taxonomy.models import AcademicLevel, Grade, Subject, Topic
from web.models import Leader, LeaderItem, SiteSetting, StaticPage
from . import forms as F


def need(*codes):
    """Page is open to anyone holding at least one of these access codes."""
    def deco(view):
        @wraps(view)
        @login_required
        def inner(request, *a, **kw):
            if not (codes_for(request.user) & set(codes)):
                raise PermissionDenied
            return view(request, *a, **kw)
        return inner
    return deco


FORMULA_CODES = ("formulas.create", "formulas.review", "formulas.publish")


def _page(request, qs, per=None):
    return Paginator(qs, per or settings.PANEL_PAGE_SIZE).get_page(request.GET.get("page"))


# ---------------------------------------------------------------- dashboard
@login_required
def dashboard(request):
    user = request.user
    if not is_panel_user(user):
        raise PermissionDenied
    codes = codes_for(user)
    pages = [{"label": p["label"], "text": p["text"], "url": page_url(p)} for p in pages_for(user, codes)]
    cards = []
    if codes & set(FORMULA_CODES):
        qs = Formula.objects.all()
        ids = any_subject_ids(user)
        if ids is not None:
            qs = qs.filter(subjects__in=ids)
        counts = dict(qs.order_by().values_list("status").annotate(n=Count("pk", distinct=True)))
        base = reverse("panel:formulas")
        cards = [("Drafts", counts.get("draft", 0), "draft"),
                 ("Awaiting review", counts.get("submitted", 0) + counts.get("in_review", 0), "submitted"),
                 ("Ready to publish", counts.get("approved", 0), "approved"),
                 ("Needs correction", counts.get("needs_correction", 0), "needs_correction"),
                 ("Published", counts.get("published", 0), "published")]
        cards = [{"label": l, "n": n, "url": f"{base}?status={s}"} for l, n, s in cards]
    roles = [] if user.is_superuser else [a.role.name for a in StaffAssignment.objects.filter(user=user).select_related("role")]
    stats = _site_stats() if (user.is_superuser or "students.view" in codes) else None
    return render(request, "panel/dashboard.html", {"pages": pages, "cards": cards, "roles": roles, "stats": stats})


def _site_stats():
    """Numbers for the owner: growth, money, what people read and search, and accounts that may be scraping."""
    from django.contrib.auth import get_user_model
    from formulas.models import FormulaView, SearchLog
    now = timezone.now()
    users = get_user_model().objects
    profiles = Profile.objects.all()
    total = profiles.count()
    paid_users = PlanRequest.objects.filter(status="paid").values("user").distinct().count()
    month = now - timedelta(days=30)
    return {
        "signups_7": users.filter(date_joined__gte=now - timedelta(days=7)).count(),
        "signups_30": users.filter(date_joined__gte=month).count(),
        "total": total,
        "premium_now": profiles.filter(premium_until__gt=now).count(),
        "trial_now": profiles.filter(trial_ends_at__gt=now).exclude(premium_until__gt=now).count(),
        "trial_ending": profiles.filter(trial_ends_at__gt=now, trial_ends_at__lte=now + timedelta(days=3)).exclude(premium_until__gt=now).count(),
        "conversion": round(100 * paid_users / total) if total else 0,
        "pending_payments": PlanRequest.objects.filter(status="pending").exclude(reference="").count(),
        "demo_published": Formula.objects.filter(status=Status.PUBLISHED, is_demo=True).count(),
        "top_formulas": list(FormulaView.objects.filter(viewed_at__gte=month).values("formula__title", "formula__slug")
                             .annotate(n=Count("pk")).order_by("-n")[:8]),
        "zero_searches": list(SearchLog.objects.filter(created_at__gte=month, result_count=0).values("query")
                              .annotate(n=Count("pk")).order_by("-n")[:10]),
        "heavy_viewers": list(FormulaView.objects.filter(viewed_at__gte=now - timedelta(days=1)).values("user__username")
                              .annotate(n=Count("formula", distinct=True)).filter(n__gte=settings.HEAVY_VIEWER_FLAG).order_by("-n")[:10]),
        "heavy_flag": settings.HEAVY_VIEWER_FLAG,
    }


# ------------------------------------------------------------------ formulas
def _visible_formulas(user):
    qs = Formula.objects.all()
    ids = any_subject_ids(user)
    return qs if ids is None else qs.filter(subjects__in=ids).distinct()


MOVES = {  # target status -> button text
    Status.SUBMITTED: "Submit for review", Status.IN_REVIEW: "Start review", Status.APPROVED: "Approve",
    Status.PUBLISHED: "Publish", Status.NEEDS_CORRECTION: "Send back for correction",
    Status.ARCHIVED: "Archive", Status.DRAFT: "Move back to draft"}


def _moves_for(user, f):
    out = []
    for target in workflow.ALLOWED.get(f.status, ()):
        action = workflow.ACTION[target]
        if not can_act(user, f, action):
            continue
        if action in ("review", "publish") and f.created_by_id == user.id and not user.is_superuser:
            continue          # nobody reviews or publishes their own formula
        out.append({"target": target, "label": MOVES[target], "needs_note": target == Status.NEEDS_CORRECTION})
    return out


def _can_edit(user, f):
    if user.is_superuser:
        return True
    return f.status in (Status.DRAFT, Status.NEEDS_CORRECTION) and can_act(user, f, "create")


@need(*FORMULA_CODES)
def formulas(request):
    qs = _visible_formulas(request.user)
    status, q = request.GET.get("status", ""), request.GET.get("q", "").strip()
    if status in Status.values:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(keywords__icontains=q))
    page = _page(request, qs.order_by("-updated_at"))
    page.object_list = prefetch(list(page.object_list), "subjects")
    for f in page.object_list:
        f.editable = _can_edit(request.user, f)
    return render(request, "panel/formulas.html", {
        "page": page, "statuses": Status.choices, "status": status, "q": q,
        "can_write": has_access(request.user, "formulas.create")})


@need(*FORMULA_CODES)
def formula_view(request, pk):
    f = get_object_or_404(_visible_formulas(request.user), pk=pk)
    return render(request, "panel/formula_view.html", {
        "f": f, "moves": _moves_for(request.user, f), "editable": _can_edit(request.user, f),
        "reviews": f.reviews.select_related("reviewer").order_by("-created_at"),
        "history": f.revisions.select_related("changed_by")[:10]})


@need(*FORMULA_CODES)
@require_POST
def formula_move(request, pk):
    f = get_object_or_404(_visible_formulas(request.user), pk=pk)
    target = request.POST.get("target", "")
    if target not in {m["target"] for m in _moves_for(request.user, f)}:
        raise PermissionDenied
    try:
        workflow.transition(f, target, request.user, notes=request.POST.get("notes", "").strip())
        messages.success(request, f"“{f.title}”: {MOVES[target].lower()} done.")
    except (ValidationError, PermissionDenied) as e:
        messages.error(request, getattr(e, "message", None) or str(e))
    return redirect("panel:formula_view", pk=pk)


@need("formulas.create")
def formula_edit(request, pk=None):
    user = request.user
    f = get_object_or_404(_visible_formulas(user), pk=pk) if pk else None
    if f and not _can_edit(user, f):
        messages.error(request, "This formula can only be edited while it is a draft or needs correction.")
        return redirect("panel:formula_view", pk=pk)
    form = F.FormulaForm(request.POST or None, instance=f, user=user)
    posting = request.method == "POST"
    # the inline rows (variables, steps...) must point at the same object that gets saved
    obj = form.save(commit=False) if (posting and form.is_valid()) else (f or Formula())
    sets = [(k, title, cls(request.POST if posting else None, instance=obj)) for k, title, cls in F.FORMSETS]
    if posting and form.is_valid() and all(s.is_valid() for _, _, s in sets):
        with transaction.atomic():
            # subjects this editor cannot see stay as they were
            ids = subject_ids(user, "create")
            keep = [] if (not f or ids is None) else list(f.subjects.exclude(pk__in=ids))
            if not f:
                obj.created_by = user
            obj.save()
            form.save_m2m()
            if keep:
                obj.subjects.add(*keep)
            for _, _, s in sets:
                s.save()
        messages.success(request, "Saved.")
        return redirect("panel:formula_view", pk=obj.pk)
    return render(request, "panel/formula_form.html", {"form": form, "sets": sets, "f": f})


# --------------------------------------------- subjects / topics / snippets / references
CRUD = {
    "subjects": dict(model=Subject, form=F.SubjectForm, perm="subjects", title="Subject", plural="Subjects",
                     cols=[("Name", "name"), ("Parent", "parent"), ("Published", "is_published")],
                     search=["name"], order=["sort_order", "name"]),
    "topics": dict(model=Topic, form=F.TopicForm, perm="topics", title="Topic", plural="Topics",
                   cols=[("Name", "name"), ("Subject", "subject"), ("Parent", "parent")],
                   search=["name", "subject__name"], order=["subject__name", "sort_order", "name"]),
    "plans": dict(model=PremiumPlan, form=F.PlanForm, perm="plans", title="Premium plan", plural="Premium plans",
                  cols=[("Name", "name"), ("Amount", "price"), ("Lasts (days)", "duration_days"), ("Most popular", "is_featured"), ("Shown", "is_active")],
                  search=["name"], order=["sort_order", "price"]),
    "plan_requests": dict(model=PlanRequest, form=F.PlanRequestForm, perm="plan_requests", title="Plan request", plural="Plan requests and payments",
                          cols=[("Student", "user"), ("Plan", "plan"), ("Amount", "amount"), ("Status", "status"), ("Reference", "reference"), ("Date", "created_at")],
                          search=["user__username", "reference", "plan__name"], order=["-created_at"]),
    "courses": dict(model=Course, form=F.CourseForm, perm="courses", title="Course", plural="Courses",
                    cols=[("Title", "title"), ("Subject", "subject"), ("Mode", "mode"), ("Price", "price"), ("Published", "is_published")],
                    search=["title", "subject__name"], order=["sort_order", "title"]),
    "live_classes": dict(model=LiveClass, form=F.LiveClassForm, perm="live_classes", title="Live class", plural="Live classes",
                         cols=[("Title", "title"), ("Subject", "subject"), ("Starts", "starts_at"), ("Seats taken", "seats_taken"), ("Published", "is_published")],
                         search=["title", "subject__name"], order=["-starts_at"]),
    "enrollments": dict(model=Enrollment, form=F.EnrollmentForm, perm="enrollments", title="Enrollment", plural="Course enrollments",
                        cols=[("Student", "user"), ("Course", "course"), ("Status", "status"), ("Note", "note"), ("Since", "created_at")],
                        search=["user__username", "course__title"], order=["-created_at"]),
    "tuition_offers": dict(model=TuitionOffer, form=F.TuitionOfferForm, perm="tuition_offers", title="Tuition offer", plural="Tuition offers",
                           cols=[("Title", "title"), ("Subject", "subject"), ("Mode", "mode"), ("Fee", "fee_label"), ("Published", "is_published")],
                           search=["title", "subject__name"], order=["sort_order", "title"]),
    "enquiries": dict(model=TuitionEnquiry, form=F.EnquiryForm, perm="enquiries", title="Tuition enquiry", plural="Tuition enquiries",
                      cols=[("Name", "name"), ("Contact", "contact"), ("Grade", "grade"), ("Status", "status"), ("Received", "created_at")],
                      search=["name", "phone", "email", "subject_wanted"], order=["-created_at"]),
    "levels": dict(model=AcademicLevel, form=F.LevelForm, perm="levels", title="Academic level", plural="Academic levels",
                   cols=[("Name", "name"), ("Code", "slug"), ("Order", "sort_order")],
                   search=["name", "slug"], order=["sort_order", "name"]),
    "grades": dict(model=Grade, form=F.GradeForm, perm="grades", title="Grade", plural="Grades",
                   cols=[("Name", "name"), ("Code", "slug"), ("Level", "level"), ("Class no.", "number"),
                         ("Usual access", "default_tier"), ("On sign-up", "is_active")],
                   search=["name", "slug"], order=["level__sort_order", "sort_order", "name"]),
    "snippets": dict(model=CodeSnippet, form=F.SnippetForm, perm="snippets", title="Code snippet", plural="Code snippets",
                     cols=[("Title", "title"), ("Language", "language"), ("Topic", "topic"), ("Premium", "is_premium")],
                     search=["title", "code"], order=["topic__name", "sort_order"]),
    "references": dict(model=Reference, form=F.ReferenceForm, perm="references", title="Reference", plural="References",
                       cols=[("Title", "title"), ("Authors", "authors"), ("Year", "year")],
                       search=["title", "authors", "doi"], order=["title"]),
    "leaders": dict(model=Leader, form=F.LeaderForm, perm="leaders", title="Owner or team profile", plural="Owner and team",
                    cols=[("Name", "name"), ("Title", "role_title"), ("Shown on site", "is_shown"), ("Order", "sort_order")],
                    search=["name", "role_title"], order=["sort_order", "name"]),
    "leader_items": dict(model=LeaderItem, form=F.LeaderItemForm, perm="leader_items", title="Qualification or achievement",
                         plural="Qualifications and achievements",
                         cols=[("Person", "leader"), ("Type", "kind_label"), ("Title", "title"), ("Year", "year")],
                         search=["title", "leader__name", "year"], order=["leader__sort_order", "leader__name", "sort_order", "id"]),
    "static_pages": dict(model=StaticPage, form=F.StaticPageForm, perm="static_pages", title="Site page", plural="Site pages",
                         cols=[("Title", "title"), ("Address", "slug"), ("In footer", "show_in_footer"), ("Published", "is_published")],
                         search=["title", "slug"], order=["sort_order", "title"]),
    "account_types": dict(model=AccountType, form=F.AccountTypeForm, perm="account_types", title="Account type",
                          plural="Account types",
                          cols=[("Name", "name"), ("Asks for grade", "asks_grade"), ("Grade access", "level_label"),
                                ("On sign-up", "is_active")],
                          search=["name"], order=["sort_order", "name"]),
}


def _cfg(request, key, action):
    """Each action (view, add, change, delete) is its own access code, e.g. subjects.add."""
    cfg = CRUD.get(key)
    if cfg is None:
        raise PermissionDenied
    if not has_access(request.user, f"{cfg['perm']}.{action}"):
        raise PermissionDenied
    return cfg


def _cell(obj, attr):
    v = getattr(obj, attr)
    if v is True:
        return "Yes"
    if v is False:
        return "No"
    return "" if v is None else str(v)


@login_required
def crud_list(request, key):
    cfg = _cfg(request, key, "view")
    can = lambda act: has_access(request.user, f"{cfg['perm']}.{act}")
    qs = cfg["model"].objects.all()
    q = request.GET.get("q", "").strip()
    if q:
        cond = Q()
        for f in cfg["search"]:
            cond |= Q(**{f"{f}__icontains": q})
        qs = qs.filter(cond)
    page = _page(request, qs.order_by(*cfg["order"]))
    rows = [{"cells": [_cell(o, a) for _, a in cfg["cols"]],
             "actions": ([("Edit", reverse("panel:crud_edit", args=[key, o.pk]))] if can("change") else [])
                        + ([("Delete", reverse("panel:crud_delete", args=[key, o.pk]))] if can("delete") else [])}
            for o in page.object_list]
    return render(request, "panel/list.html", {
        "title": cfg["plural"], "heads": [h for h, _ in cfg["cols"]], "rows": rows, "page": page, "q": q,
        "new_url": reverse("panel:crud_new", args=[key]) if can("add") else None,
        "new_label": f"Add {cfg['title'].lower()}"})


@login_required
def crud_edit(request, key, pk=None):
    cfg = _cfg(request, key, "change" if pk else "add")
    obj = get_object_or_404(cfg["model"], pk=pk) if pk else None
    form = cfg["form"](request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{cfg['title']} saved.")
        return redirect("panel:crud_list", key=key)
    return render(request, "panel/form.html", {
        "title": f"{'Edit' if obj else 'Add'} {cfg['title'].lower()}", "form": form,
        "back": reverse("panel:crud_list", args=[key])})


@login_required
def crud_delete(request, key, pk):
    cfg = _cfg(request, key, "delete")
    obj = get_object_or_404(cfg["model"], pk=pk)
    back = reverse("panel:crud_list", args=[key])
    if request.method == "POST":
        try:
            obj.delete()
            messages.success(request, f"{cfg['title']} deleted.")
        except ProtectedError as e:
            note = e.args[0] if (e.args and not e.protected_objects) else ""
            messages.error(request, (note + ". Move those first." if note else
                                     "This is still used by other records. Move or delete those first."))
        return redirect(back)
    return render(request, "panel/confirm.html", {"title": f"Delete {cfg['title'].lower()}?", "obj": obj, "back": back})


# ------------------------------------------------------------------ site logo
@need("site_settings.view", "site_settings.change")
def branding(request):
    obj = SiteSetting.current() or SiteSetting()
    can_change = has_access(request.user, "site_settings.change")
    form = F.SiteSettingForm(request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST":
        if not can_change:
            raise PermissionDenied
        if form.is_valid():
            form.save()
            messages.success(request, "Logo and icon saved. Press Ctrl+F5 if the browser tab still shows the old icon.")
            return redirect("panel:branding")
    return render(request, "panel/branding.html", {
        "title": "Site logo and icon", "form": form, "obj": obj, "can_change": can_change})


# ------------------------------------------------------------------ students
@need("students.view")
def students(request):
    qs = Profile.objects.select_related("user", "account_type")
    q, grade = request.GET.get("q", "").strip(), request.GET.get("grade", "")
    atype = request.GET.get("type", "")
    if re.fullmatch(r"[0-9a-fA-F]{24}", atype):
        qs = qs.filter(account_type_id=ObjectId(atype))
    if q:
        qs = qs.filter(Q(user__username__icontains=q) | Q(user__email__icontains=q))
    if grade:
        qs = qs.filter(grade=grade)
    page = _page(request, qs.order_by("-created_at"))
    names = Grade.name_map()
    for p in page.object_list:
        p.grade_label = names.get(p.grade, p.grade)
    return render(request, "panel/students.html", {
        "page": page, "q": q, "grade": grade, "grades": list(names.items()),
        "types": AccountType.objects.all(), "atype": atype})


@need("students.grant")
@require_POST
def student_grant(request, pk):
    p = get_object_or_404(Profile, pk=pk)
    now = timezone.now()
    days = settings.PREMIUM_GRANT_DAYS
    p.premium_until = max(p.premium_until or now, now) + timedelta(days=days)
    p.save()
    log(request.user, "premium.grant", p.user.username, f"+{days} days, now until {p.premium_until:%d %b %Y}")
    messages.success(request, f"{p.user.username}: premium extended by {days} days.")
    return redirect(request.POST.get("back") or "panel:students")


# --------------------------------------------------------------------- roles
def _labels():
    return {c["code"]: c["label"] for _, items in grouped() for c in items}


@need("roles.view")
def roles(request):
    user = request.user
    rows = []
    for r in StaffRole.objects.annotate(n=Count("assignments")):
        acts = []
        if has_access(user, "roles.change"):
            acts.append(("Edit", reverse("panel:role_edit", args=[r.pk])))
        if has_access(user, "roles.delete"):
            acts.append(("Delete", reverse("panel:role_delete", args=[r.pk])))
        rows.append({"cells": [r.name, summary(r.access), r.grade_label, "Required" if r.require_2fa else "—", str(r.n)], "actions": acts})
    return render(request, "panel/list.html", {
        "title": "Roles", "heads": ["Role", "Can do", "Grades it can see", "Two-factor", "Users"], "rows": rows,
        "intro": "A role is a named set of permissions. Create one, tick what it may do, then give it to people under Staff access.",
        "new_url": reverse("panel:role_new") if has_access(user, "roles.add") else None, "new_label": "Add role"})


@login_required
def role_edit(request, pk=None):
    if not has_access(request.user, "roles.change" if pk else "roles.add"):
        raise PermissionDenied
    role = get_object_or_404(StaffRole, pk=pk) if pk else None
    before = expand(role.access) if role else set()
    grades_before = ({"*"} if role.all_grades else set(role.grades or [])) if role else set()
    form = F.RoleForm(request.POST or None, instance=role, editor=request.user)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        after = expand(saved.access)
        added, removed = sorted(after - before), sorted(before - after)
        grades_after = {"*"} if saved.all_grades else set(saved.grades or [])
        g_add, g_rem = sorted(grades_after - grades_before), sorted(grades_before - grades_after)
        log(request.user, "role.update" if role else "role.create", saved.name,
            "; ".join(x for x in (f"added {', '.join(added)}" if added else "",
                                  f"removed {', '.join(removed)}" if removed else "",
                                  f"grades added {', '.join(g_add)}" if g_add else "",
                                  f"grades removed {', '.join(g_rem)}" if g_rem else "") if x))
        messages.success(request, "Role saved. Users with this role get the change immediately.")
        return redirect("panel:roles")
    selected = set(request.POST.getlist("access")) if request.method == "POST" else before
    mine = form.editor_codes
    groups = [(g, [{**c, "checked": c["code"] in selected, "locked": c["code"] not in mine} for c in items])
              for g, items in grouped()]
    return render(request, "panel/role_form.html", {"form": form, "groups": groups, "role": role})


@need("roles.delete")
def role_delete(request, pk):
    role = get_object_or_404(StaffRole, pk=pk)
    if request.method == "POST":
        n = role.assignments.count()
        log(request.user, "role.delete", role.name, f"{n} user(s) lost it")
        role.delete()
        messages.success(request, "Role deleted.")
        return redirect("panel:roles")
    n = role.assignments.count()
    return render(request, "panel/confirm.html", {
        "title": "Delete role?", "obj": role, "back": reverse("panel:roles"),
        "warn": f"{n} user(s) have this role and will lose its access." if n else ""})


# --------------------------------------------------------------------- staff
@need("staff.view")
def staff(request):
    q = request.GET.get("q", "").strip()
    qs = StaffAssignment.objects.select_related("user", "role", "user__totp")
    if q:
        qs = qs.filter(Q(user__username__icontains=q) | Q(role__name__icontains=q))
    page = _page(request, qs)
    page.object_list = prefetch(list(page.object_list), "subjects")
    rows = []
    for a in page.object_list:
        acts = []
        if has_access(request.user, "staff.change"):
            acts += [("Edit", reverse("panel:staff_edit", args=[a.pk])),
                     ("Pause" if a.is_active else "Resume", reverse("panel:staff_toggle", args=[a.pk]), "post")]
            if request.user.is_superuser and getattr(a.user, "totp", None):
                acts.append(("Reset 2FA", reverse("panel:staff_reset2fa", args=[a.pk]), "post"))
        if has_access(request.user, "staff.delete"):
            acts.append(("Remove", reverse("panel:staff_delete", args=[a.pk])))
        rows.append({"cells": [a.user.username, a.role.name,
                               ", ".join(s.name for s in a.subjects.all()) or "Not subject based",
                               "Active" if a.is_active else "Paused", a.qualification],
                     "actions": acts, "muted": not a.is_active})
    return render(request, "panel/list.html", {
        "title": "Staff", "heads": ["User", "Role", "Subjects", "Status", "Qualification"], "rows": rows, "page": page, "q": q,
        "intro": "Each line gives one user one role. When they sign in they are taken to the pages that role allows. "
                 "Pause switches the access off without deleting it.",
        "new_url": reverse("panel:staff_new") if has_access(request.user, "staff.add") else None,
        "new_label": "Give a role to a user"})


@login_required
def staff_edit(request, pk=None):
    if not has_access(request.user, "staff.change" if pk else "staff.add"):
        raise PermissionDenied
    a = get_object_or_404(StaffAssignment, pk=pk) if pk else None
    form = F.StaffForm(request.POST or None, instance=a, editor=request.user)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            saved = form.save()
        log(request.user, "staff.update" if a else "staff.assign", saved.user.username,
            f"{saved.role.name}; subjects: {', '.join(s.name for s in saved.subjects.all()) or 'none'}; "
            f"{'active' if saved.is_active else 'paused'}" + ("; account created" if form.new_user else ""))
        messages.success(request, "Saved.")
        return redirect("panel:staff")
    scoped = json.dumps({str(r.pk): bool(set(r.access or []) & SCOPED_CODES) for r in StaffRole.objects.all()})
    return render(request, "panel/staff_form.html", {"form": form, "a": a, "scoped": scoped})


def _not_self(request, a):
    if a.user_id == request.user.id and not request.user.is_superuser:
        messages.error(request, "You cannot pause or remove your own access. Ask another administrator.")
        return False
    return True


@need("staff.delete")
def staff_delete(request, pk):
    a = get_object_or_404(StaffAssignment, pk=pk)
    if not _not_self(request, a):
        return redirect("panel:staff")
    if request.method == "POST":
        log(request.user, "staff.remove", a.user.username, a.role.name)
        a.delete()
        messages.success(request, "Role removed from user.")
        return redirect("panel:staff")
    return render(request, "panel/confirm.html", {"title": "Remove this role from the user?", "obj": a, "back": reverse("panel:staff")})


@need("staff.change")
@require_POST
def staff_toggle(request, pk):
    a = get_object_or_404(StaffAssignment, pk=pk)
    if _not_self(request, a):
        a.is_active = not a.is_active
        a.save(update_fields=["is_active"])
        log(request.user, "staff.resume" if a.is_active else "staff.pause", a.user.username, a.role.name)
        messages.success(request, f"{a.user.username} as {a.role.name}: {'active again' if a.is_active else 'paused'}.")
    return redirect("panel:staff")


@need("staff.change")
@require_POST
def staff_reset2fa(request, pk):
    if not request.user.is_superuser:
        raise PermissionDenied
    a = get_object_or_404(StaffAssignment, pk=pk)
    TOTPDevice.objects.filter(user=a.user).delete()
    log(request.user, "2fa.reset", a.user.username)
    messages.success(request, f"Two-factor reset for {a.user.username}. They set it up again at next sign-in.")
    return redirect("panel:staff")


# ------------------------------------------------------------------ activity log
@need("audit.view")
def audit(request):
    q = request.GET.get("q", "").strip()
    qs = AuditLog.objects.all()
    if q:
        qs = qs.filter(Q(actor_name__icontains=q) | Q(action__icontains=q) | Q(target__icontains=q) | Q(detail__icontains=q))
    page = _page(request, qs, 40)
    rows = [{"cells": [f"{e.created_at:%d %b %Y %H:%M}", e.actor_name or "(system)", e.action, e.target, e.detail], "actions": []}
            for e in page.object_list]
    return render(request, "panel/list.html", {
        "title": "Activity log", "heads": ["When (UTC)", "Who", "What", "About", "Details"], "rows": rows, "page": page, "q": q,
        "intro": "Changes to roles, staff access, premium and two-factor. Entries cannot be edited."})


# ----------------------------------------------------------------- two-factor
@login_required
def security(request):
    user = request.user
    if not is_panel_user(user):
        raise PermissionDenied
    dev = TOTPDevice.objects.filter(user=user).first()
    verified = bool(request.session.get("otp_ok"))
    forced = role_requires_2fa(user)
    ident = str(user.pk)
    if request.method == "POST":
        action, code = request.POST.get("action", ""), request.POST.get("code", "")
        if action == "start" and dev is None:
            TOTPDevice.objects.create(user=user, secret=totp.new_secret())
            return redirect("panel:security")
        if action in ("setup", "verify", "disable") and dev:
            if lockout.is_locked("otp", ident):
                messages.error(request, "Too many wrong codes. Wait 15 minutes and try again.")
            elif not totp.verify(dev.secret, code):
                lockout.fail("otp", ident)
                messages.error(request, "That code is not right. Check your phone's clock and try the newest code.")
            else:
                lockout.clear("otp", ident)
                if action == "setup" and not dev.confirmed:
                    dev.confirmed = True
                    dev.save(update_fields=["confirmed"])
                    request.session["otp_ok"] = True
                    log(user, "2fa.enable", user.username)
                    messages.success(request, "Two-factor sign-in is on.")
                    return redirect(landing_url(user))
                if action == "verify" and dev.confirmed:
                    request.session["otp_ok"] = True
                    return redirect(landing_url(user))
                if action == "disable" and dev.confirmed and not forced:
                    dev.delete()
                    log(user, "2fa.disable", user.username)
                    messages.success(request, "Two-factor sign-in is off.")
                    return redirect("panel:security")
        return redirect("panel:security")
    state = "none" if dev is None else ("pending" if not dev.confirmed else ("ask" if not verified else "on"))
    ctx = {"state": state, "forced": forced, "standalone": state in ("none", "pending", "ask")}
    if state == "pending":
        ctx.update(secret=dev.secret, uri=totp.uri(dev.secret, user.username),
                   spaced=" ".join(dev.secret[i:i + 4] for i in range(0, 32, 4)))
    return render(request, "panel/security.html", ctx)
