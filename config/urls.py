from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("candidates/", include("candidates.urls")),
    path("sources/", include("candidates.source_urls")),
    path("openings/", include("openings.urls")),
    path("applications/", include("applications.urls")),
]
