from django.urls import path

from candidates.views import (
    CandidateArchiveView,
    CandidateCreateView,
    CandidateDeleteView,
    CandidateDetailView,
    CandidateListView,
    CandidateUpdateView,
)

app_name = "candidates"

urlpatterns = [
    path("", CandidateListView.as_view(), name="list"),
    path("new/", CandidateCreateView.as_view(), name="create"),
    path("<int:pk>/", CandidateDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", CandidateUpdateView.as_view(), name="update"),
    path("<int:pk>/archive/", CandidateArchiveView.as_view(), name="archive"),
    path("<int:pk>/unarchive/", CandidateArchiveView.as_view(archive=False), name="unarchive"),
    path("<int:pk>/delete/", CandidateDeleteView.as_view(), name="delete"),
]
