from django.urls import path

from applications.views import PipelineBoardView
from openings.views import OpeningCreateView, OpeningDetailView, OpeningListView, OpeningUpdateView

app_name = "openings"

urlpatterns = [
    path("", OpeningListView.as_view(), name="list"),
    path("new/", OpeningCreateView.as_view(), name="create"),
    path("<int:pk>/", OpeningDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", OpeningUpdateView.as_view(), name="update"),
    # The board belongs to the applications app, but lives under its opening.
    path("<int:pk>/board/", PipelineBoardView.as_view(), name="board"),
]
