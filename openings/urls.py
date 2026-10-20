from django.urls import path

from openings.views import OpeningCreateView, OpeningDetailView, OpeningListView, OpeningUpdateView

app_name = "openings"

urlpatterns = [
    path("", OpeningListView.as_view(), name="list"),
    path("new/", OpeningCreateView.as_view(), name="create"),
    path("<int:pk>/", OpeningDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", OpeningUpdateView.as_view(), name="update"),
]
