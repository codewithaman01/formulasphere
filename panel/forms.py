import re
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from django.utils.text import slugify
from accounts.models import AccountType, PlanRequest, PremiumPlan, StaffAssignment, StaffRole
from accounts.permissions import ALL_CODES, LEGACY, SCOPED_CODES, expand
from accounts.scope import codes_for, grade_grants, subject_ids
from formulas.models import (Assumption, CodeSnippet, DerivationStep, Example, Formula, FormulaReference,
                             FormulaVariable, Reference)
from learning.models import Course, Enrollment, LiveClass, TuitionEnquiry, TuitionOffer
from taxonomy.models import AcademicLevel, Grade, Subject, Topic
from web.models import Leader, LeaderItem, SiteSetting, StaticPage, StoredImage

from formulas.validators import validate_latex, validate_calc_expression

User = get_user_model()

class Styled(forms.ModelForm):
    """Adds the panel's CSS classes and an optional slug that fills itself in."""
    slug_from = "name"
    slug_len = 50

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        for f in self.fields.values():
            if isinstance(f.widget, forms.CheckboxInput):
                continue
            if isinstance(f.widget, forms.Textarea):
                f.widget.attrs.setdefault("rows", 4)
        if "slug" in self.fields:
            self.fields["slug"].required = False
            self.fields["slug"].help_text = "Leave empty to create it from the name."

    def clean(self):
        data = super().clean()
        if "slug" in self.fields and not data.get("slug"):
            data["slug"] = slugify(data.get(self.slug_from) or "")[:self.slug_len]
            if not data["slug"]:
                self.add_error(self.slug_from, "Enter this first so a web address can be made from it.")
        return data


class DbImageMixin:
    """Lets a form upload pictures that are kept in the database (see StoredImage).
    Set `images = {"photo": ("Photo", 600), ...}`: field name -> (label, longest side in pixels)."""
    images = {}
    ACCEPT = "image/png,image/jpeg,image/webp"

    def add_image_fields(self):
        for name, (label, px) in self.images.items():
            current = getattr(self.instance, name + "_id", None)
            self.fields[name + "_upload"] = forms.ImageField(
                required=False, label=label + (" (replace)" if current else ""),
                help_text="JPG, PNG or WebP, up to 3 MB. Shrunk to fit %d pixels." % px,
                widget=forms.ClearableFileInput(attrs={"accept": self.ACCEPT}))
            self.fields[name + "_upload"].widget.is_required = False
            if current:
                self.fields["remove_" + name] = forms.BooleanField(required=False, label="Remove the current " + label.lower())

    def clean(self):
        data = super().clean()
        self._new_images = {}
        for name, (label, px) in self.images.items():
            up = data.get(name + "_upload")
            if up:
                try:
                    self._new_images[name] = StoredImage.from_upload(up, px)
                except ValidationError as e:
                    self.add_error(name + "_upload", e)
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        old = []
        for name in self.images:
            new = self._new_images.get(name)
            if new or self.cleaned_data.get("remove_" + name):
                if getattr(obj, name + "_id"):
                    old.append(getattr(obj, name + "_id"))
                setattr(obj, name, new)
        if commit:
            obj.save()
            self.save_m2m()
            StoredImage.objects.filter(pk__in=old).delete()      # the replaced pictures are no longer used anywhere
        return obj


class SubjectForm(Styled):
    class Meta:
        model = Subject
        fields = ["name", "slug", "description", "parent", "icon", "is_published", "sort_order"]


class TopicForm(Styled):
    class Meta:
        model = Topic
        fields = ["subject", "parent", "name", "slug", "description", "explanation", "sort_order"]


class SnippetForm(Styled):
    class Meta:
        model = CodeSnippet
        fields = ["topic", "language", "title", "explanation", "code", "expected_output", "is_premium", "sort_order"]


class ReferenceForm(Styled):
    class Meta:
        model = Reference
        fields = ["title", "authors", "publisher", "year", "doi", "url", "licence", "attribution"]


def grade_choices():
    """[(slug, 'Class 9'), ...] read from the Grades table each time, never typed into the code."""
    return [(g.slug, g.name) for g in Grade.objects.order_by("level__sort_order", "sort_order", "name")]


class LevelForm(Styled):
    class Meta:
        model = AcademicLevel
        fields = ["name", "slug", "description", "sort_order"]


class GradeForm(Styled):
    slug_len = 20

    class Meta:
        model = Grade
        fields = ["name", "slug", "level", "number", "default_tier", "default_difficulty", "sort_order", "is_active"]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        if self.instance.pk:          # people hold this code on their profile, so it stays as it is
            self.fields["slug"].disabled = True
            self.fields["slug"].help_text = "The code cannot be changed after the grade is created."
        else:
            self.fields["slug"].help_text = "Leave empty to create it from the name (for example class-9)."


class AccountTypeForm(Styled):
    default_grade = forms.ChoiceField(
        required=False, label="Main level",
        help_text="For types that do not ask for a grade: their own level. Not used when 'ask for grade' is ticked.")
    allowed_grades = forms.MultipleChoiceField(
        required=False, widget=forms.CheckboxSelectMultiple, label="Also open these grades",
        help_text="Extra grades this type may open, besides its own. Ignored when 'open every grade' is ticked.")

    class Meta:
        model = AccountType
        fields = ["name", "slug", "description", "asks_grade", "default_grade", "all_grades", "allowed_grades",
                  "is_active", "sort_order"]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["default_grade"].choices = [("", "—")] + grade_choices()
        self.fields["allowed_grades"].choices = grade_choices()

    def clean(self):
        data = super().clean()
        if not data.get("asks_grade") and not data.get("default_grade"):
            self.add_error("default_grade", "Choose the main level, because this type does not ask for a grade.")
        if data.get("asks_grade"):
            data["default_grade"] = ""
        if data.get("all_grades"):
            data["allowed_grades"] = []
        return data


# ---------------------------------------------------------------- formulas
class FormulaForm(Styled):
    slug_from = "title"

    def clean_latex(self):
        v = validate_latex(self.cleaned_data.get("latex"))
        if not v:
            raise ValidationError("Enter the formula in LaTeX.")
        return v

    def clean_calc_expression(self):
        return validate_calc_expression(self.cleaned_data.get("calc_expression"))

    class Meta:
        model = Formula
        fields = ["title", "slug", "latex", "plain_text", "short_explanation", "detailed_explanation",
                  "subjects", "topics", "levels", "related", "keywords", "difficulty", "access_tier",
                  "min_class", "source_verification", "calc_expression"]
        widgets = {"subjects": forms.CheckboxSelectMultiple, "levels": forms.CheckboxSelectMultiple,
                   "topics": forms.SelectMultiple, "related": forms.SelectMultiple}

    def __init__(self, *a, user=None, **kw):
        super().__init__(*a, **kw)
        ids = subject_ids(user, "create")           # None = every subject
        if ids is not None:
            self.fields["subjects"].queryset = Subject.objects.filter(pk__in=ids)
            self.fields["topics"].queryset = Topic.objects.filter(subject_id__in=ids)
        self.fields["topics"].required = False
        self.fields["related"].required = False
        if self.instance.pk:
            self.fields["related"].queryset = Formula.objects.exclude(pk=self.instance.pk)


class StepForm(forms.ModelForm):
    def clean_latex(self):
        return validate_latex(self.cleaned_data.get("latex"))


class VariableForm(forms.ModelForm):
    def clean_symbol(self):
        return validate_latex(self.cleaned_data.get("symbol"))

    def clean_unit(self):
        return validate_latex(self.cleaned_data.get("unit"))


def _fs(model, fields, extra=1, form=forms.ModelForm):
    return inlineformset_factory(Formula, model, form=form, fields=fields, extra=extra, can_delete=True)


FORMSETS = [
    ("variables", "Variables", _fs(FormulaVariable, ["symbol", "name", "meaning", "unit", "constraints", "sort_order"], 1, VariableForm)),
    ("steps", "Derivation steps", _fs(DerivationStep, ["step_number", "latex", "explanation", "reference"], 0, StepForm)),
    ("assumptions", "Assumptions", _fs(Assumption, ["description", "validity", "sort_order"], 0)),
    ("examples", "Worked examples", _fs(Example, ["title", "problem", "given", "solution", "result", "units", "difficulty"], 0)),
    ("refs", "Sources", _fs(FormulaReference, ["reference", "locator", "claim_supported", "is_verified"], 0)),
]


# ------------------------------------------------------------------- roles
class RoleForm(forms.ModelForm):
    """Name, description, and the tick-list of access codes.

    Someone who is not a superuser can only tick what they hold themselves, and
    anything they cannot see on a role is kept as it was."""
    access = forms.MultipleChoiceField(required=False, choices=[(c, c) for c in sorted(ALL_CODES | set(LEGACY))])
    grades = forms.MultipleChoiceField(
        required=False, widget=forms.CheckboxSelectMultiple, label="Grades this role can see",
        help_text="People with this role can open formulas of these grades on the site, without a trial or premium.")

    class Meta:
        model = StaffRole
        fields = ["name", "description", "default_subjects", "require_2fa", "all_grades"]
        labels = {"name": "Role name"}
        widgets = {"default_subjects": forms.CheckboxSelectMultiple}

    def __init__(self, *a, editor=None, **kw):
        super().__init__(*a, **kw)
        self.editor_codes = codes_for(editor)
        # only a superuser may switch two-factor on or off for a role
        self.fields["require_2fa"].disabled = not (editor and editor.is_superuser)
        self.fields["default_subjects"].required = False
        self.fields["require_2fa"].help_text = "People with this role must enter an authenticator-app code at sign-in. Only a superuser can change this."
        self.old = expand(self.instance.access) if self.instance.pk else set()
        self.initial["access"] = sorted(self.old)
        # grades: a role editor can only hand out grades they hold themselves
        every, mine = grade_grants(editor) if editor else (False, set())
        self.editor_every_grade, self.editor_grades = every, mine
        self.fields["all_grades"].disabled = not every
        self.fields["all_grades"].help_text = ("People with this role can open every grade, without a trial or premium."
                                               + ("" if every else " You can only switch this on if you hold it yourself."))
        self.fields["grades"].choices = [c for c in grade_choices() if every or c[0] in mine]
        self.old_grades = set(self.instance.grades or []) if self.instance.pk else set()
        self.initial["grades"] = sorted(self.old_grades)

    def save(self, commit=True):
        chosen = expand(self.cleaned_data["access"]) & self.editor_codes
        self.instance.access = sorted(chosen | (self.old - self.editor_codes))
        picked = set(self.cleaned_data.get("grades") or [])
        if self.editor_every_grade:
            self.instance.grades = sorted(picked)
        else:   # grades the editor does not hold stay as they were
            self.instance.grades = sorted((picked & self.editor_grades) | (self.old_grades - self.editor_grades))
        return super().save(commit)


# ------------------------------------------------------------------- staff
class StaffForm(forms.ModelForm):
    """Give a role to a user. Type an existing username, or fill in email and password
    to create the account at the same time."""
    username = forms.CharField(max_length=150, help_text="Existing username, or a new one to create.")
    email = forms.EmailField(required=False, help_text="Only needed when creating a new account.")
    password = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False),
                               help_text="Only needed when creating a new account.")

    field_order = ["username", "email", "password", "role", "subjects", "qualification", "is_active"]

    class Meta:
        model = StaffAssignment
        fields = ["role", "subjects", "qualification", "is_active"]
        widgets = {"subjects": forms.CheckboxSelectMultiple}

    def __init__(self, *a, editor=None, **kw):
        super().__init__(*a, **kw)
        self.new_user = None
        mine = codes_for(editor)
        allowed = [r.pk for r in StaffRole.objects.all() if expand(r.access) <= mine]
        self.fields["role"].queryset = StaffRole.objects.filter(pk__in=allowed)
        self.fields["subjects"].required = False
        self.fields["subjects"].help_text = "Leave empty to use the role's usual subjects, if it has any."
        if self.instance.pk:
            self.fields["username"].initial = self.instance.user.username
            self.fields["username"].disabled = True
            self.fields["email"].disabled = self.fields["password"].disabled = True

    def clean(self):
        data = super().clean()
        role = data.get("role")
        if role and (set(role.access or []) & SCOPED_CODES) and not data.get("subjects"):
            defaults = role.default_subjects.all()
            if defaults:                       # fall back to the role's usual subjects
                data["subjects"] = defaults
            else:
                self.add_error("subjects", "This role works per subject. Choose at least one subject.")
        username = (data.get("username") or "").strip()
        if not username or self.errors.get("username"):
            return data
        if self.instance.pk:
            user = self.instance.user
        else:
            user = User.objects.filter(username__iexact=username).first()
            if user is None:
                if not data.get("password") or not data.get("email"):
                    self.add_error("username", "No user has this username. To create one, fill in email and password too.")
                    return data
                try:
                    validate_password(data["password"], User(username=username, email=data["email"]))
                except ValidationError as e:
                    self.add_error("password", e)
                    return data
                self.new_user = User(username=username, email=data["email"])
                self.new_user.set_password(data["password"])
            elif user.is_superuser:
                self.add_error("username", "This user is a superuser and already has full access.")
                return data
        if user and role and StaffAssignment.objects.filter(user=user, role=role).exclude(pk=self.instance.pk).exists():
            self.add_error("role", "This user already has this role. Edit that assignment instead.")
        self.target_user = user
        return data

    def save(self, commit=True):
        if self.new_user is not None:
            self.new_user.save()
            self.target_user = self.new_user
        if not self.instance.pk:
            self.instance.user = self.target_user
        return super().save(commit)


class _Grades:
    """Grade tick boxes read from the Grades table."""
    def grade_boxes(self, label="Grades"):
        self.fields["grades"].widget = forms.CheckboxSelectMultiple()
        self.fields["grades"].queryset = Grade.objects.order_by("level__sort_order", "sort_order", "name")
        self.fields["grades"].label = label


class CourseForm(_Grades, Styled):
    slug_from = "title"

    class Meta:
        model = Course
        fields = ["title", "slug", "subject", "grades", "topics", "summary", "description", "syllabus", "teacher", "teacher_name",
                  "mode", "duration_weeks", "price", "is_published", "sort_order"]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.grade_boxes("Who it is for")
        self.fields["topics"].queryset = Topic.objects.select_related("subject").order_by("subject__name", "name")
        self.fields["topics"].help_text = "Hold Ctrl (or Cmd) to pick several."


class LiveClassForm(_Grades, Styled):
    slug_from = "title"
    starts_at = forms.DateTimeField(label="Starts at", input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"],
                                    widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
                                    help_text="In the server's time zone.")

    class Meta:
        model = LiveClass
        fields = ["title", "slug", "course", "subject", "topic", "grades", "teacher", "teacher_name", "description", "starts_at",
                  "duration_minutes", "join_url", "capacity", "recording_url", "is_published"]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.grade_boxes("Who it is for")


class EnrollmentForm(Styled):
    class Meta:
        model = Enrollment
        fields = ["user", "course", "status", "note"]


class TuitionOfferForm(_Grades, Styled):
    slug_from = "title"

    class Meta:
        model = TuitionOffer
        fields = ["title", "slug", "subject", "grades", "mode", "area", "fee_per_hour", "fee_note", "group_size", "description",
                  "is_published", "sort_order"]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.grade_boxes("Who it is for")


class EnquiryForm(Styled):
    class Meta:
        model = TuitionEnquiry
        fields = ["name", "phone", "email", "grade", "subject_wanted", "offer", "message", "status", "staff_note"]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["grade"] = forms.ChoiceField(required=False, choices=[("", "—")] + grade_choices())


class PlanForm(Styled):
    class Meta:
        model = PremiumPlan
        fields = ["name", "slug", "tagline", "price", "original_price", "duration_days", "features", "description",
                  "is_featured", "is_active", "sort_order"]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["features"].widget.attrs["rows"] = 7


class PlanRequestForm(Styled):
    class Meta:
        model = PlanRequest
        fields = ["user", "plan", "amount", "status", "reference", "staff_note"]
        help_texts = {"status": "Set to Paid once you have received the money. The plan's days are added to the student's Premium automatically, once."}


class LeaderForm(DbImageMixin, Styled):
    images = {"photo": ("Photo", 600)}

    class Meta:
        model = Leader
        fields = ["name", "role_title", "short_bio", "about", "email", "website", "is_shown", "sort_order"]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.add_image_fields()
        self.order_fields(["name", "role_title", "photo_upload", "remove_photo"])
        self.fields["about"].widget.attrs["rows"] = 8


class LeaderItemForm(Styled):
    class Meta:
        model = LeaderItem
        fields = ["leader", "kind", "title", "detail", "year", "sort_order"]


class SiteSettingForm(DbImageMixin, Styled):
    images = {"logo": ("Logo", 512), "favicon": ("Icon", 128)}

    class Meta:
        model = SiteSetting
        fields = []

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.add_image_fields()
        self.fields["logo_upload"].help_text = "Shown in the header next to the site name. A square picture with a transparent background (PNG) works best. " + self.fields["logo_upload"].help_text
        self.fields["favicon_upload"].help_text = "Small icon in the browser tab. Optional: if empty, the logo is used. Square, at least 64x64. " + self.fields["favicon_upload"].help_text


class StaticPageForm(Styled):
    class Meta:
        model = StaticPage
        fields = ["title", "slug", "body", "show_in_footer", "sort_order", "is_published"]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["body"].widget.attrs["rows"] = 16
