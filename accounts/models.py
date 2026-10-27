from django.conf import settings
from django.db import models
from django_mongodb_backend import transaction
from django_mongodb_backend.fields import ArrayField
from django.utils import timezone
from taxonomy.models import Grade


class AccountType(models.Model):
    """Who a person is when they sign up: Student, Teacher, Professor, Research Scholar...

    Created and edited by an admin in the panel (Account types). Only types that
    "ask for grade" show the grade list on the sign-up form. The other types get
    `default_grade` instead, which decides which formulas they can open."""
    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=60, unique=True)
    description = models.CharField(max_length=200, blank=True, help_text="Shown under the name on sign-up, optional")
    asks_grade = models.BooleanField(
        "ask for grade", default=False,
        help_text="Tick for Student-like types: the person then picks their grade while creating the account.")
    default_grade = models.CharField(
        "formula level", max_length=20, blank=True,
        help_text="For types that do not ask for grade: the grade whose formulas they can open (a Grade slug).")
    all_grades = models.BooleanField(
        "open every grade", default=False,
        help_text="Tick to let this type open formulas of every grade and level.")
    allowed_grades = ArrayField(
        models.CharField(max_length=20), verbose_name="also open these grades", default=list, blank=True,
        help_text="Extra grades this type may open, besides its own. Ignored when 'open every grade' is ticked.")
    is_active = models.BooleanField("show on sign-up", default=True,
                                    help_text="Untick to hide this type from new sign-ups. Existing users keep it.")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    @property
    def level_label(self):
        """Shown in the panel list: what formulas this type can open."""
        if self.all_grades:
            return "Every grade"
        names = Grade.name_map()
        base = "Own grade" if self.asks_grade else (names.get(self.default_grade, self.default_grade) or "—")
        extra = [names.get(g, g) for g in (self.allowed_grades or [])]
        return base + (" + " + ", ".join(extra) if extra else "")


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    account_type = models.ForeignKey(AccountType, null=True, blank=True, on_delete=models.PROTECT, related_name="profiles")
    grade = models.CharField(max_length=20, help_text="Slug of a Grade (see Grades in the panel)")
    trial_ends_at = models.DateTimeField()
    premium_until = models.DateTimeField(null=True, blank=True, help_text="Set after payment is received")
    created_at = models.DateTimeField(auto_now_add=True)
    trial_reminded_at = models.DateTimeField(null=True, blank=True, editable=False)
    premium_reminded_for = models.DateTimeField(null=True, blank=True, editable=False,
                                                help_text="The premium_until date the last reminder email was about")

    def __str__(self):
        return f"{self.user} ({self.identity})"

    @property
    def grade_obj(self):
        if not hasattr(self, "_grade_obj"):
            self._grade_obj = Grade.objects.filter(slug=self.grade).select_related("level").first()
        return self._grade_obj

    @property
    def grade_name(self):
        """Readable grade, 'Class 9'. Falls back to the stored code if the grade was removed."""
        return self.grade_obj.name if self.grade_obj else self.grade

    @property
    def identity(self):
        """'Student · Class 9', or just 'Teacher' for types that have no grade."""
        t = self.account_type
        if t is None:
            return self.grade_name
        return f"{t.name} · {self.grade_name}" if t.asks_grade else t.name

    @property
    def opens_every_grade(self):
        return bool(self.account_type and self.account_type.all_grades)

    def open_grades(self):
        """Grade codes this person may open: their own, plus any extra grades given to their account type."""
        t = self.account_type
        out = []
        for g in [self.grade] + (list(t.allowed_grades or []) if t else []):
            if g and g not in out:
                out.append(g)
        return out

    @property
    def is_premium(self):
        return bool(self.premium_until and self.premium_until > timezone.now())

    @property
    def in_trial(self):
        return self.trial_ends_at > timezone.now()

    @property
    def plan(self):
        return "premium" if self.is_premium else ("trial" if self.in_trial else "expired")


# ---------------------------------------------------------------------------
# Staff roles. An admin builds a role in the panel by ticking what it may open
# (see permissions.py), then gives the role to a user, limited to chosen subjects
# for the subject-scoped items.
# ---------------------------------------------------------------------------
from taxonomy.models import Subject


class StaffRole(models.Model):
    name = models.CharField(max_length=80, unique=True)
    description = models.CharField(max_length=300, blank=True)
    access = ArrayField(models.CharField(max_length=60), verbose_name="access", default=list, blank=True,
                        help_text="List of access codes, chosen in the panel")
    default_subjects = models.ManyToManyField(
        Subject, blank=True, related_name="+",
        help_text="Used when this role is given to someone without choosing subjects. Copied at that moment.")
    require_2fa = models.BooleanField("require two-factor sign-in", default=False)
    all_grades = models.BooleanField(
        "can see every grade", default=False,
        help_text="People with this role can open formulas of every grade and level, without a trial or premium.")
    grades = ArrayField(
        models.CharField(max_length=20), verbose_name="can see these grades", default=list, blank=True,
        help_text="Grades whose formulas people with this role can open on the site. Ignored when 'every grade' is ticked.")
    # Legacy columns from the old fixed checkboxes. Kept only so `manage.py upgrade_roles`
    # can convert old roles without losing data. Safe to delete once that has been run.
    can_create = models.BooleanField(default=False, editable=False)
    can_review = models.BooleanField(default=False, editable=False)
    can_publish = models.BooleanField(default=False, editable=False)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def has(self, code):
        return code in (self.access or [])

    @property
    def grade_label(self):
        if self.all_grades:
            return "Every grade"
        names = Grade.name_map()
        return ", ".join(names.get(g, g) for g in (self.grades or [])) or "—"


class StaffAssignment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assignments")
    role = models.ForeignKey(StaffRole, on_delete=models.CASCADE, related_name="assignments")
    subjects = models.ManyToManyField(Subject, blank=True, related_name="staff")
    qualification = models.CharField(max_length=300, blank=True, help_text="Why this person is trusted for these subjects")
    is_active = models.BooleanField("active", default=True, help_text="Untick to pause this access without deleting it")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["user__username", "role__name"]
        constraints = [models.UniqueConstraint(fields=["user", "role"], name="uniq_user_role")]

    def __str__(self):
        return f"{self.user} as {self.role}"


class TOTPDevice(models.Model):
    """Authenticator-app (TOTP) secret for two-factor sign-in."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="totp")
    secret = models.CharField(max_length=32)
    confirmed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class AuditLog(models.Model):
    """Who changed access, and when. Rows are only ever added."""
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    actor_name = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=60)
    target = models.CharField(max_length=200, blank=True)
    detail = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["-created_at"])]

    def __str__(self):
        return f"{self.actor_name} {self.action} {self.target}"


class PremiumPlan(models.Model):
    """A Premium plan shown on the Premium page. Everything on the page comes from these rows."""
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80, unique=True)
    tagline = models.CharField(max_length=200, blank=True, help_text="One line under the plan name.")
    price = models.DecimalField("amount", max_digits=9, decimal_places=2, help_text="What the student pays for this plan.")
    original_price = models.DecimalField("old amount", max_digits=9, decimal_places=2, null=True, blank=True,
                                         help_text="Optional. Shown crossed out, with the saving worked out for you.")
    duration_days = models.PositiveIntegerField("lasts (days)", default=30, help_text="Premium days added when payment is confirmed: 30 = a month, 365 = a year.")
    features = models.TextField("what they get", blank=True, help_text="One benefit per line. Each line gets a tick on the page.")
    description = models.TextField(blank=True, help_text="Optional longer text under the benefits.")
    is_featured = models.BooleanField("highlight as most popular", default=False)
    is_active = models.BooleanField("show on the Premium page", default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "price"]

    def __str__(self):
        return f"{self.name} ({self.price:g})"

    @property
    def feature_list(self):
        return [l.strip() for l in self.features.splitlines() if l.strip()]

    @property
    def period_label(self):
        d = self.duration_days
        if d % 365 == 0:
            n = d // 365
            return "year" if n == 1 else f"{n} years"
        if d % 30 == 0:
            n = d // 30
            return "month" if n == 1 else f"{n} months"
        return f"{d} days"

    @property
    def per_month(self):
        """Price for 30 days, so plans of different length can be compared."""
        return round(self.price * 30 / self.duration_days, 2) if self.duration_days else self.price

    @property
    def saving_percent(self):
        if self.original_price and self.original_price > self.price:
            return int((self.original_price - self.price) * 100 / self.original_price)
        return 0


class PlanRequest(models.Model):
    """A student's choice of a plan. When staff set it to Paid the Premium days are added, exactly once."""
    STATUS = [("pending", "Waiting for payment"), ("paid", "Paid"), ("cancelled", "Cancelled")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="plan_requests")
    plan = models.ForeignKey(PremiumPlan, on_delete=models.PROTECT, related_name="requests")
    amount = models.DecimalField(max_digits=9, decimal_places=2, help_text="The amount at the time of choosing the plan.")
    status = models.CharField(max_length=10, choices=STATUS, default="pending")
    reference = models.CharField("payment reference", max_length=120, blank=True, help_text="Entered by the student, for example the UPI transaction id.")
    staff_note = models.CharField(max_length=200, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True, editable=False)
    gateway_order_id = models.CharField(max_length=60, blank=True, db_index=True, editable=False)
    gateway_payment_id = models.CharField(max_length=60, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} - {self.plan.name} ({self.get_status_display()})"

    def save(self, *a, **kw):
        if self.amount is None:
            self.amount = self.plan.price
        if self.pk and self.applied_at is None:
            # never write an empty applied_at over a date another request has just stored
            stored = PlanRequest.objects.filter(pk=self.pk).values_list("applied_at", flat=True).first()
            if stored is not None:
                self.applied_at = stored
        super().save(*a, **kw)
        if self.status == "paid" and self.applied_at is None:
            self.apply()

    def apply(self):
        """Add the plan's days to the person's Premium. Safe to call twice: it only ever happens once."""
        from datetime import timedelta
        profile = Profile.objects.filter(user=self.user).first()
        if profile is None or self.applied_at is not None:
            return
        now = timezone.now()
        with transaction.atomic():
            # MongoDB has no row locks, so claim the request first: only one caller can change applied_at from
            # empty to a date. A second caller (a webhook retry, a double click) finds it taken and stops here.
            if not PlanRequest.objects.filter(pk=self.pk, applied_at__isnull=True).update(applied_at=now):
                self.applied_at = PlanRequest.objects.values_list("applied_at", flat=True).get(pk=self.pk)
                return
            profile.premium_until = max(profile.premium_until or now, now) + timedelta(days=self.plan.duration_days)
            profile.save()
        self.applied_at = now
        from . import emails
        emails.send_payment_confirmed(self, profile)


class UserSession(models.Model):
    """Which sign-ins (devices) an account has. The oldest is signed out when the limit is passed."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="device_sessions")
    session_key = models.CharField(max_length=40, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
