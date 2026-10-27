"""Django admin is now only a back-up tool for the superuser. Day-to-day work,
including roles and staff, happens in the panel at /panel/."""
from datetime import timedelta
from django.conf import settings
from django.contrib import admin
from django.utils import timezone
from .models import AccountType, Profile, StaffAssignment, StaffRole

admin.site.site_header = "FormulaSphere (superuser tools)"


@admin.action(description="Grant extra days of premium (see FS_PREMIUM_GRANT_DAYS)")
def grant_30(modeladmin, request, queryset):
    now = timezone.now()
    for p in queryset:
        p.premium_until = max(p.premium_until or now, now) + timedelta(days=settings.PREMIUM_GRANT_DAYS)
        p.save()


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "account_type", "grade", "trial_ends_at", "premium_until")
    list_filter = ("account_type", "grade")
    search_fields = ("user__username", "user__email")
    actions = [grant_30]


@admin.register(StaffRole)
class StaffRoleAdmin(admin.ModelAdmin):
    list_display = ("name", "description")


@admin.register(StaffAssignment)
class StaffAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "qualification")
    filter_horizontal = ("subjects",)
    autocomplete_fields = ("user",)
    search_fields = ("user__username",)


@admin.register(AccountType)
class AccountTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "asks_grade", "default_grade", "is_active", "sort_order")
    prepopulated_fields = {"slug": ("name",)}
