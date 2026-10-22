from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("candidates/", include("candidates.urls")),
    path("sources/", include("candidates.source_urls")),
    path("openings/", include("openings.urls")),
    path("skills/", include("openings.skill_urls")),
    path("applications/", include("applications.urls")),
    path("attention/", include("notifications.urls")),
    path("in-progress/", include("openings.in_progress_urls")),
]
