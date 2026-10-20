"""Source URLs, mounted at /sources/. Sources live in the candidates app, in their own namespace."""

from django.urls import path

from candidates.views import (
    SourceActivationView,
    SourceCreateView,
    SourceListView,
    SourceRenameView,
)

app_name = "sources"

urlpatterns = [
    path("", SourceListView.as_view(), name="list"),
    path("new/", SourceCreateView.as_view(), name="create"),
    path("<int:pk>/edit/", SourceRenameView.as_view(), name="update"),
    path("<int:pk>/retire/", SourceActivationView.as_view(activate=False), name="retire"),
    path("<int:pk>/reactivate/", SourceActivationView.as_view(activate=True), name="reactivate"),
]
