"""The Admin in-progress view, mounted at /in-progress/. It lives in the openings app, in its own
namespace."""

from django.urls import path

from openings.views import InProgressView

app_name = "in_progress"

urlpatterns = [
    path("", InProgressView.as_view(), name="list"),
]
