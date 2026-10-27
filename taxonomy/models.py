import uuid
from django.db import models
from django.db.models import ProtectedError
from django.utils.text import slugify


class Subject(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    icon = models.CharField("icon identifier", max_length=60, blank=True)
    is_published = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        indexes = [models.Index(fields=["is_published", "sort_order"])]

    def __str__(self):
        return self.name


class AcademicLevel(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(unique=True)
    sort_order = models.PositiveIntegerField(default=0)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["sort_order"]

    def __str__(self):
        return self.name


class Curriculum(models.Model):
    name = models.CharField(max_length=120)
    region = models.CharField(max_length=80, blank=True)
    authority = models.CharField("education authority", max_length=120, blank=True)
    version = models.CharField(max_length=40, blank=True)
    level = models.ForeignKey(AcademicLevel, on_delete=models.PROTECT, related_name="curricula")
    source_url = models.URLField(blank=True)

    class Meta:
        verbose_name_plural = "curricula"

    def __str__(self):
        return f"{self.name} {self.version}".strip()


class Course(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    level = models.ForeignKey(AcademicLevel, on_delete=models.PROTECT, related_name="courses")
    curriculum = models.ForeignKey(Curriculum, null=True, blank=True, on_delete=models.SET_NULL)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Topic(models.Model):
    name = models.CharField(max_length=140)
    slug = models.SlugField()
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="topics")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    description = models.TextField(blank=True, help_text="One short line shown in lists.")
    explanation = models.TextField(blank=True, help_text="The full explanation shown at the top of the topic page. A blank line starts a new paragraph.")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [models.UniqueConstraint(fields=["subject", "slug"], name="uniq_topic_slug_per_subject")]

    def __str__(self):
        return f"{self.subject}: {self.name}"


class Grade(models.Model):
    """One step a person can be placed on: Class 1 ... Class 12, Undergraduate, Postgraduate, Research.

    Nothing in the code knows the list. An admin adds, renames, reorders or hides grades in the panel
    (Grades). The `slug` is what is stored on a person's profile, so it cannot be changed once created.

    A grade belongs to an academic level. `number` is used for school classes: a Class 9 student opens
    school formulas whose first class is 9 or lower. Leave it empty for a whole level (Undergraduate).
    """
    TIERS = [("basic", "Basic (free trial)"), ("premium", "Premium")]
    DIFFICULTIES = [("beginner", "Beginner"), ("intermediate", "Intermediate"), ("advanced", "Advanced")]

    name = models.CharField(max_length=60)
    slug = models.SlugField(max_length=20, unique=True,
                            help_text="Short code stored on profiles, for example class-9. Cannot be changed later.")
    level = models.ForeignKey(AcademicLevel, on_delete=models.PROTECT, related_name="grades")
    number = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Class number for school grades. Leave empty for a whole level such as Undergraduate.")
    default_tier = models.CharField("usual access for new formulas", max_length=10, choices=TIERS, default="premium",
                                    help_text="Used when formulas are loaded from the data files.")
    default_difficulty = models.CharField("usual difficulty for new formulas", max_length=20, choices=DIFFICULTIES,
                                          default="beginner")
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField("show on sign-up", default=True,
                                    help_text="Untick to hide this grade from new sign-ups. People who already have it keep it.")

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    @classmethod
    def name_map(cls):
        """{slug: name} in one query, for lists that show many people."""
        return dict(cls.objects.values_list("slug", "name"))

    def usage(self):
        """How many things still point at this grade: {'people': n, 'account types': n, 'roles': n}."""
        from accounts.models import AccountType, Profile, StaffRole
        out = {
            "people": Profile.objects.filter(grade=self.slug).count(),
            "account types": AccountType.objects.filter(models.Q(default_grade=self.slug)
                                                        | models.Q(allowed_grades__contains=[self.slug])).count(),
            "roles": StaffRole.objects.filter(grades__contains=[self.slug]).count(),
        }
        return {k: v for k, v in out.items() if v}

    def delete(self, *a, **kw):
        used = self.usage()
        if used:
            raise ProtectedError("Grade is still used by " + ", ".join(f"{v} {k}" for k, v in used.items()), set())
        return super().delete(*a, **kw)
