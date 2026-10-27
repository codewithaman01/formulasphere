"""Single place that decides who can open which formula.

Nothing here knows a list of grades. A grade is a row in the Grade table (edited in the panel under
Grades). A person opens a formula when one of these is true:
  * they are a superuser;
  * one of their active staff roles grants the formula's grade (role "can see these grades");
  * the formula is in their own grade or in grades their account type adds, and their plan allows it
    (premium, or a trial and a basic formula).
"""
from django.db.models import Q
from taxonomy.models import Grade


def get_profile(user):
    if not user.is_authenticated:
        return None
    try:
        return user.profile
    except Exception:
        return None


class GradeRules:
    """A set of grades turned into 'which formulas match'. Built once per person per request."""

    def __init__(self, every=False, slugs=()):
        self.every = bool(every)
        self.pairs = []                       # (academic level slug, class number or None)
        slugs = [s for s in dict.fromkeys(slugs) if s]
        if slugs and not self.every:
            self.pairs = [(g.level.slug, g.number)
                          for g in Grade.objects.filter(slug__in=slugs).select_related("level")]

    @property
    def empty(self):
        return not self.every and not self.pairs

    def allows(self, formula):
        if self.every:
            return True
        levels = {l.slug for l in formula.levels.all()}
        return any(slug in levels and (n is None or formula.min_class is None or formula.min_class <= n)
                   for slug, n in self.pairs)

    def q(self):
        """Django Q for the same rule. Matches nothing when no grade is held."""
        cond = Q(pk__in=[])
        for slug, n in self.pairs:
            part = Q(levels__slug=slug)
            if n is not None:
                part &= Q(min_class__isnull=True) | Q(min_class__lte=n)
            cond |= part
        return cond


def own_rules(profile):
    """Grades from the person's profile: their own grade plus extras given to their account type."""
    return GradeRules(profile.opens_every_grade, profile.open_grades())


def staff_rules(user):
    """Grades given by the person's active staff roles."""
    if not user.is_authenticated:
        return GradeRules()
    cached = getattr(user, "_fs_staff_rules", None)
    if cached is None:
        from .models import StaffAssignment
        every, slugs = False, []
        for a in StaffAssignment.objects.filter(user=user, is_active=True).select_related("role"):
            every = every or a.role.all_grades
            slugs += list(a.role.grades or [])
        cached = user._fs_staff_rules = GradeRules(every, slugs)
    return cached


def _own(user, profile):
    cached = getattr(user, "_fs_own_rules", None)
    if cached is None:
        cached = user._fs_own_rules = own_rules(profile)
    return cached


def in_grade(profile, formula):
    """True if the formula is for a grade this profile may open (own grade, account-type extras, every grade)."""
    return own_rules(profile).allows(formula)


def can_view(user, formula):
    if user.is_superuser:
        return True
    if staff_rules(user).allows(formula):          # a role that grants this grade: open, no plan needed
        return True
    p = get_profile(user)
    if not p or not _own(user, p).allows(formula):
        return False
    if p.is_premium:
        return True
    return p.in_trial and formula.access_tier == "basic"


def restrict_queryset(user, qs):
    """People only see formulas for the grades they may open."""
    if user.is_superuser:
        return qs
    p, staff = get_profile(user), staff_rules(user)
    if staff.every or (p and p.opens_every_grade):
        return qs
    if not p and staff.empty:
        return qs                                  # no grades held at all: the cards show as locked
    cond = staff.q()
    if p:
        cond |= _own(user, p).q()
    # a sub-query keeps the original queryset's ordering and search ranking intact
    return qs.filter(pk__in=qs.model.objects.filter(cond).values("pk"))
