from django.contrib import admin
from . import converters  # noqa: F401  (registers <objectid:...>)
from django.urls import include, path
urlpatterns = [path("admin/", admin.site.urls), path("panel/", include("panel.urls")), path("api/v1/", include("api.urls")), path("", include("learning.urls")), path("", include("accounts.urls")), path("", include("web.urls"))]
