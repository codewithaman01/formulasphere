from django.contrib import admin
from .models import Leader, LeaderItem, SiteSetting


class ItemInline(admin.TabularInline):
    model = LeaderItem
    extra = 1


@admin.register(Leader)
class LeaderAdmin(admin.ModelAdmin):
    list_display = ("name", "role_title", "is_shown", "sort_order")
    inlines = [ItemInline]


@admin.register(SiteSetting)
class SiteSettingAdmin(admin.ModelAdmin):
    """Logo and tab icon. Only one record can exist; it is edited, never added twice or deleted."""
    def has_add_permission(self, request):
        return not SiteSetting.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        from django.shortcuts import redirect
        obj = SiteSetting.current()
        if obj:
            return redirect("admin:web_sitesetting_change", obj.pk)
        return super().changelist_view(request, extra_context)

    def response_add(self, request, obj, post_url_continue=None):
        from django.shortcuts import redirect
        return redirect("admin:web_sitesetting_change", obj.pk)
