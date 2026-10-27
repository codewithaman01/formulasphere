"""Courses, live classes and tuition. Grades, subjects and topics are the same tables the formulas use,
so nothing here has its own list of them."""
from datetime import timedelta
from django.conf import settings
from django.db import models
from django.utils import timezone
from taxonomy.models import Grade, Subject, Topic


class Course(models.Model):
    MODES = [("self_paced", "Self-paced"), ("live", "Live classes"), ("blended", "Live and self-paced")]
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="courses")
    grades = models.ManyToManyField(Grade, blank=True, related_name="courses", help_text="Who the course is for.")
    topics = models.ManyToManyField(Topic, blank=True, related_name="courses", help_text="Topics the course covers; they link to the formulas.")
    summary = models.CharField(max_length=300, blank=True, help_text="One line shown in lists.")
    description = models.TextField(blank=True, help_text="What the course teaches and who it suits. A blank line starts a new paragraph.")
    syllabus = models.TextField(blank=True, help_text="One lesson or chapter per line.")
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="courses_taught")
    teacher_name = models.CharField(max_length=120, blank=True, help_text="Shown if there is no teacher account.")
    mode = models.CharField(max_length=12, choices=MODES, default="self_paced")
    duration_weeks = models.PositiveSmallIntegerField(null=True, blank=True)
    price = models.DecimalField(max_digits=9, decimal_places=2, default=0, help_text="0 means free. Paid courses stay 'pending' until staff confirm payment.")
    is_published = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "title"]

    def __str__(self):
        return self.title

    @property
    def is_free(self):
        return self.price == 0

    @property
    def lessons(self):
        return [l.strip() for l in self.syllabus.splitlines() if l.strip()]

    @property
    def teacher_label(self):
        if self.teacher_id:
            return self.teacher.get_full_name() or self.teacher.get_username()
        return self.teacher_name

    @property
    def grade_label(self):
        return ", ".join(g.name for g in self.grades.all()) or "All grades"


class Enrollment(models.Model):
    STATUS = [("pending", "Waiting for payment"), ("active", "Active"), ("cancelled", "Cancelled")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="enrollments")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    status = models.CharField(max_length=10, choices=STATUS, default="pending")
    note = models.CharField(max_length=200, blank=True, help_text="For staff, for example the payment reference.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["user", "course"], name="uniq_enrollment")]

    def __str__(self):
        return f"{self.user} in {self.course}"


class LiveClass(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    course = models.ForeignKey(Course, null=True, blank=True, on_delete=models.SET_NULL, related_name="live_classes",
                               help_text="Leave empty for a stand-alone class. Course students are registered automatically.")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="live_classes")
    topic = models.ForeignKey(Topic, null=True, blank=True, on_delete=models.SET_NULL, related_name="live_classes")
    grades = models.ManyToManyField(Grade, blank=True, related_name="live_classes")
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="classes_taught")
    teacher_name = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    starts_at = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField(default=60)
    join_url = models.URLField(blank=True, help_text="Meeting link (Google Meet, Zoom...). Only shown to people who registered, shortly before the start.")
    capacity = models.PositiveIntegerField(null=True, blank=True, help_text="Leave empty for no limit.")
    recording_url = models.URLField(blank=True, help_text="Added after the class, shown to registered people.")
    is_published = models.BooleanField(default=False)

    class Meta:
        ordering = ["starts_at"]

    def __str__(self):
        return self.title

    @property
    def ends_at(self):
        return self.starts_at + timedelta(minutes=self.duration_minutes)

    @property
    def is_over(self):
        return timezone.now() > self.ends_at

    def join_open(self, now=None):
        """The link is shown from LIVE_JOIN_EARLY_MINUTES before the start until the class ends."""
        now = now or timezone.now()
        early = timedelta(minutes=getattr(settings, "LIVE_JOIN_EARLY_MINUTES", 15))
        return self.starts_at - early <= now <= self.ends_at

    @property
    def seats_taken(self):
        return self.registrations.count()

    @property
    def is_full(self):
        return self.capacity is not None and self.seats_taken >= self.capacity

    @property
    def teacher_label(self):
        if self.teacher_id:
            return self.teacher.get_full_name() or self.teacher.get_username()
        return self.teacher_name or (self.course.teacher_label if self.course_id else "")


class ClassRegistration(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="class_registrations")
    live_class = models.ForeignKey(LiveClass, on_delete=models.CASCADE, related_name="registrations")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["user", "live_class"], name="uniq_class_registration")]


class TuitionOffer(models.Model):
    MODES = [("online", "Online"), ("home", "At the student's home"), ("centre", "At the tutor's place"), ("any", "Online or in person")]
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="tuition_offers")
    grades = models.ManyToManyField(Grade, blank=True, related_name="tuition_offers")
    mode = models.CharField(max_length=10, choices=MODES, default="any")
    area = models.CharField(max_length=200, blank=True, help_text="Where, for example the neighbourhood and city.")
    fee_per_hour = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    fee_note = models.CharField(max_length=200, blank=True, help_text="Shown instead of a number if you prefer, e.g. 'Ask for the monthly fee'.")
    group_size = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Students per batch. Leave empty for one-to-one.")
    description = models.TextField(blank=True)
    is_published = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "title"]

    def __str__(self):
        return self.title

    @property
    def fee_label(self):
        if self.fee_per_hour is not None:
            return f"{self.fee_per_hour:g} per hour"
        return self.fee_note or "Ask for the fee"

    @property
    def grade_label(self):
        return ", ".join(g.name for g in self.grades.all()) or "All grades"


class TuitionEnquiry(models.Model):
    STATUS = [("new", "New"), ("contacted", "Contacted"), ("trial", "Trial class booked"), ("enrolled", "Enrolled"), ("closed", "Closed")]
    offer = models.ForeignKey(TuitionOffer, null=True, blank=True, on_delete=models.SET_NULL, related_name="enquiries")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="tuition_enquiries")
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    grade = models.CharField(max_length=20, blank=True, help_text="Slug of a Grade")
    subject_wanted = models.CharField(max_length=120, blank=True)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="new")
    staff_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "tuition enquiries"

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

    @property
    def contact(self):
        return " · ".join(x for x in (self.phone, self.email) if x)
