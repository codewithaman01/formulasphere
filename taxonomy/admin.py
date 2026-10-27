from django.contrib import admin
from .models import AcademicLevel, Course, Curriculum, Grade, Subject, Topic


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "is_published", "sort_order")
    list_filter = ("is_published",)
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("name", "subject", "parent", "sort_order")
    list_filter = ("subject",)
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(AcademicLevel)
class LevelAdmin(admin.ModelAdmin):
    list_display = ("name", "sort_order")
    prepopulated_fields = {"slug": ("name",)}


admin.site.register(Curriculum)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "level", "number", "is_active", "sort_order")
    list_filter = ("level", "is_active")
