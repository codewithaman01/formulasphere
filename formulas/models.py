import uuid
from django.conf import settings
from django.db import models
from taxonomy.models import AcademicLevel, Subject, Topic


class Status(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted for review"
    IN_REVIEW = "in_review", "In review"
    APPROVED = "approved", "Approved"
    PUBLISHED = "published", "Published"
    NEEDS_CORRECTION = "needs_correction", "Needs correction"
    ARCHIVED = "archived", "Archived"


class SourceVerification(models.TextChoices):
    UNVERIFIED = "unverified", "No source checked"
    SOURCE_CHECKED = "source_checked", "Matches a cited source"


class Difficulty(models.TextChoices):
    BEGINNER = "beginner", "Beginner"
    INTERMEDIATE = "intermediate", "Intermediate"
    ADVANCED = "advanced", "Advanced"


class Reference(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=300)
    authors = models.CharField(max_length=300, blank=True)
    publisher = models.CharField("journal or publisher", max_length=200, blank=True)
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    doi = models.CharField(max_length=120, blank=True)
    url = models.URLField(blank=True)
    licence = models.CharField(max_length=80, blank=True)
    attribution = models.TextField(blank=True)

    def __str__(self):
        return self.title


class Formula(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    latex = models.TextField("canonical LaTeX")
    plain_text = models.CharField(max_length=300, blank=True)
    short_explanation = models.CharField(max_length=300)
    detailed_explanation = models.TextField(blank=True)
    subjects = models.ManyToManyField(Subject, related_name="formulas")
    topics = models.ManyToManyField(Topic, blank=True, related_name="formulas")
    levels = models.ManyToManyField(AcademicLevel, related_name="formulas")
    related = models.ManyToManyField("self", blank=True)
    keywords = models.CharField(max_length=300, blank=True, help_text="Comma separated")
    difficulty = models.CharField(max_length=20, choices=Difficulty.choices, default=Difficulty.BEGINNER)
    access_tier = models.CharField(max_length=10, choices=[("basic", "Basic (free trial)"), ("premium", "Premium")], default="premium")
    min_class = models.PositiveSmallIntegerField(null=True, blank=True, help_text="School formulas: first class (1-12) that studies this")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    source_verification = models.CharField(max_length=20, choices=SourceVerification.choices,
                                           default=SourceVerification.UNVERIFIED)
    is_demo = models.BooleanField(default=False, help_text="Demonstration record, not reviewed content")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    last_reviewed_at = models.DateTimeField(null=True, blank=True)
    calc_expression = models.CharField("calculator expression", max_length=300, blank=True,
        help_text="Optional. Adds a calculator to the page. Write the right-hand side with plain names, for example 0.5*m*v^2 or pi*r^2. Each name becomes an input box.")

    class Meta:
        ordering = ["title"]
        permissions = [("review_formula", "Can review formulas"), ("publish_formula", "Can publish formulas")]
        indexes = [models.Index(fields=["status", "-updated_at"])]

    def __str__(self):
        return self.title


class FormulaVariable(models.Model):
    formula = models.ForeignKey(Formula, on_delete=models.CASCADE, related_name="variables")
    symbol = models.CharField("symbol (LaTeX)", max_length=60)
    name = models.CharField(max_length=120)
    meaning = models.TextField(blank=True)
    unit = models.CharField("SI unit (LaTeX, blank if dimensionless)", max_length=60, blank=True)
    constraints = models.CharField(max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order"]


class DerivationStep(models.Model):
    formula = models.ForeignKey(Formula, on_delete=models.CASCADE, related_name="derivation_steps")
    step_number = models.PositiveIntegerField()
    latex = models.TextField(blank=True)
    explanation = models.TextField(blank=True)
    reference = models.ForeignKey(Reference, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["step_number"]
        constraints = [models.UniqueConstraint(fields=["formula", "step_number"], name="uniq_step_per_formula")]


class Assumption(models.Model):
    formula = models.ForeignKey(Formula, on_delete=models.CASCADE, related_name="assumptions")
    description = models.TextField()
    validity = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order"]


class Example(models.Model):
    formula = models.ForeignKey(Formula, on_delete=models.CASCADE, related_name="examples")
    title = models.CharField(max_length=200)
    problem = models.TextField()
    given = models.TextField(blank=True)
    solution = models.TextField(blank=True)
    result = models.CharField(max_length=200, blank=True)
    units = models.CharField(max_length=60, blank=True)
    difficulty = models.CharField(max_length=20, choices=Difficulty.choices, default=Difficulty.BEGINNER)


class FormulaReference(models.Model):
    formula = models.ForeignKey(Formula, on_delete=models.CASCADE, related_name="formula_references")
    reference = models.ForeignKey(Reference, on_delete=models.PROTECT)
    locator = models.CharField("page, section or equation", max_length=120, blank=True)
    claim_supported = models.CharField(max_length=300, blank=True)
    is_verified = models.BooleanField(default=False)


class FormulaRevision(models.Model):
    formula = models.ForeignKey(Formula, on_delete=models.CASCADE, related_name="revisions")
    version = models.PositiveIntegerField()
    snapshot = models.JSONField()
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    reason = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version"]
        constraints = [models.UniqueConstraint(fields=["formula", "version"], name="uniq_revision")]


class Review(models.Model):
    class Decision(models.TextChoices):
        APPROVE = "approve", "Approve"
        CORRECT = "correct", "Needs correction"

    formula = models.ForeignKey(Formula, on_delete=models.CASCADE, related_name="reviews")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    decision = models.CharField(max_length=10, choices=Decision.choices)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class CodeSnippet(models.Model):
    class Language(models.TextChoices):
        PYTHON = "python", "Python"
        JAVA = "java", "Java"

    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="snippets")
    language = models.CharField(max_length=10, choices=Language.choices)
    title = models.CharField(max_length=160)
    explanation = models.CharField(max_length=300, blank=True)
    code = models.TextField()
    expected_output = models.TextField(blank=True)
    is_premium = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "language"]
        constraints = [models.UniqueConstraint(fields=["topic", "title", "language"], name="uniq_snippet")]


class Bookmark(models.Model):
    """A formula a person saved to come back to."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookmarks")
    formula = models.ForeignKey(Formula, on_delete=models.CASCADE, related_name="bookmarks")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["user", "formula"], name="one_bookmark_per_formula")]


class FormulaView(models.Model):
    """One row per person per formula per visit (at most one every 10 minutes). Used for Recently viewed,
    the dashboard and to spot accounts that open an unusual number of formulas."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="formula_views")
    formula = models.ForeignKey(Formula, on_delete=models.CASCADE, related_name="views")
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-viewed_at"]
        indexes = [models.Index(fields=["user", "-viewed_at"]), models.Index(fields=["-viewed_at"])]


class SearchLog(models.Model):
    """What people searched for and how many formulas they got. Zero-result searches show what content is missing."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    query = models.CharField(max_length=200)
    result_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["-created_at"])]


class PracticeAttempt(models.Model):
    """A student's own mark on a practice question: did they get it or not."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="practice_attempts")
    example = models.ForeignKey(Example, on_delete=models.CASCADE, related_name="attempts")
    got_it = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "-created_at"])]
