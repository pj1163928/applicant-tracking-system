from django.urls import path

from candidates.views import (
    CandidateCreateView,
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
]
