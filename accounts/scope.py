"""What a staff member may open, and for which subjects. Everything reads the role's
tick-list (StaffRole.access); nothing here knows the role names."""
from django.urls import reverse
from config.prefetch import prefetch
from .models import StaffAssignment, TOTPDevice
from .permissions import ALL_CODES, PAGES, expand

# workflow actions -> access code
ACTION_CODE = {"create": "formulas.create", "review": "formulas.review", "publish": "formulas.publish"}


def _assignments(user):
    return prefetch(list(StaffAssignment.objects.filter(user=user, is_active=True).select_related("role")), "subjects")


def codes_for(user):
    """All access codes the user holds through any of their roles."""
    if not user.is_authenticated:
        return set()
    if user.is_superuser:
        return set(ALL_CODES)
    held = set()
    for a in _assignments(user):
        held |= expand(a.role.access)
    return held & ALL_CODES          # ignore codes that no longer exist


def has_access(user, code):
    return code in codes_for(user)


def pages_for(user, codes=None):
    codes = codes_for(user) if codes is None else codes
    return [p for p in PAGES if codes & set(p["any"])]


def page_url(page):
    name, kwargs = page["url"]
    return reverse(name, kwargs=kwargs)


def is_panel_user(user):
    return user.is_authenticated and (user.is_superuser or StaffAssignment.objects.filter(user=user, is_active=True).exists())


def landing_url(user):
    """Where a user goes right after signing in."""
    if is_panel_user(user):
        pages = pages_for(user)
        return page_url(pages[0]) if len(pages) == 1 else reverse("panel:dashboard")
    return reverse("explore")


def subject_ids(user, action):
    """Subject ids the user may act on for 'create' / 'review' / 'publish'.
    None means every subject (superuser)."""
    if user.is_superuser:
        return None
    if not user.is_authenticated:
        return set()
    code = ACTION_CODE[action]
    ids = set()
    for a in _assignments(user):
        if a.role.has(code):
            ids |= {s.pk for s in a.subjects.all()}
    return ids


def any_subject_ids(user):
    """Subjects the user can see formulas for under any formula action."""
    if user.is_superuser:
        return None
    return subject_ids(user, "create") | subject_ids(user, "review") | subject_ids(user, "publish")


def can_act(user, formula, action):
    ids = subject_ids(user, action)
    return True if ids is None else bool(ids & set(formula.subjects.values_list("id", flat=True)))


def grade_grants(user):
    """(every, slugs): the grades the user's roles let them see. A superuser has every grade.
    Someone editing a role can only hand out grades they hold themselves."""
    if user.is_superuser:
        return True, set()
    every, slugs = False, set()
    for a in _assignments(user):
        every = every or a.role.all_grades
        slugs |= set(a.role.grades or [])
    return every, slugs


def needs_2fa(user):
    """True if this user must pass an authenticator-app code each session: they turned it on
    themselves, or one of their active roles requires it."""
    if not user.is_authenticated:
        return False
    if TOTPDevice.objects.filter(user=user, confirmed=True).exists():
        return True
    return StaffAssignment.objects.filter(user=user, is_active=True, role__require_2fa=True).exists()


def role_requires_2fa(user):
    return StaffAssignment.objects.filter(user=user, is_active=True, role__require_2fa=True).exists()
