from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from accounts.scope import can_act, subject_ids
from taxonomy.models import Subject, Topic
from . import workflow
from .models import (Assumption, DerivationStep, Example, Formula, FormulaReference, FormulaRevision,
                     FormulaVariable, Reference, Review, Status)


class VariableInline(admin.TabularInline):
    model = FormulaVariable; extra = 1


class StepInline(admin.StackedInline):
    model = DerivationStep; extra = 0


class AssumptionInline(admin.TabularInline):
    model = Assumption; extra = 0


class ExampleInline(admin.StackedInline):
    model = Example; extra = 0


class FormulaRefInline(admin.TabularInline):
    model = FormulaReference; extra = 0


def _action(target, label):
    def run(modeladmin, request, queryset):
        for f in queryset:
            try:
                workflow.transition(f, target, request.user)
            except (ValidationError, PermissionDenied) as e:
                messages.error(request, f"{f.title}: {getattr(e, 'message', e)}")
    run.short_description = label
    run.__name__ = f"to_{target}"
    return run


@admin.register(Formula)
class FormulaAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "access_tier", "min_class", "difficulty", "source_verification", "is_demo", "updated_at")
    list_filter = ("status", "access_tier", "difficulty", "source_verification", "is_demo", "subjects", "levels")
    search_fields = ("title", "keywords", "short_explanation")
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ("subjects", "topics", "levels", "related")
    readonly_fields = ("status", "created_by", "reviewed_by", "published_at", "last_reviewed_at")
    inlines = [VariableInline, StepInline, AssumptionInline, ExampleInline, FormulaRefInline]
    actions = [_action(Status.SUBMITTED, "Submit for review"), _action(Status.IN_REVIEW, "Start review"),
               _action(Status.APPROVED, "Approve"), _action(Status.PUBLISHED, "Publish"),
               _action(Status.NEEDS_CORRECTION, "Mark as needs correction"), _action(Status.ARCHIVED, "Archive")]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        ids = subject_ids(request.user, "create") | subject_ids(request.user, "review") | subject_ids(request.user, "publish")
        return qs.filter(subjects__in=ids).distinct()

    def formfield_for_manytomany(self, db_field, request, **kw):
        ids = subject_ids(request.user, "create")
        if ids is not None and db_field.name == "subjects":
            kw["queryset"] = Subject.objects.filter(pk__in=ids)
        elif ids is not None and db_field.name == "topics":
            kw["queryset"] = Topic.objects.filter(subject_id__in=ids)
        return super().formfield_for_manytomany(db_field, request, **kw)

    def has_change_permission(self, request, obj=None):
        ok = super().has_change_permission(request, obj)
        if not ok or obj is None or request.user.is_superuser:
            return ok
        return obj.status in (Status.DRAFT, Status.NEEDS_CORRECTION) and can_act(request.user, obj, "create")

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Reference)
class ReferenceAdmin(admin.ModelAdmin):
    list_display = ("title", "authors", "year", "doi")
    search_fields = ("title", "authors", "doi")


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("formula", "reviewer", "decision", "created_at")
    def has_add_permission(self, r): return False
    def has_change_permission(self, r, o=None): return False


@admin.register(FormulaRevision)
class RevisionAdmin(admin.ModelAdmin):
    list_display = ("formula", "version", "changed_by", "created_at")
    def has_add_permission(self, r): return False
    def has_change_permission(self, r, o=None): return False


from .models import CodeSnippet


@admin.register(CodeSnippet)
class CodeSnippetAdmin(admin.ModelAdmin):
    list_display = ("title", "language", "topic", "is_premium")
    list_filter = ("language", "is_premium", "topic__subject")
    search_fields = ("title", "code")
