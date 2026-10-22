"""Staff URLs, mounted at /staff/. Staff departure lives in the accounts app, in its own
namespace."""

from django.urls import path

from accounts.views import StaffDeactivateView, StaffListView

app_name = "staff"

urlpatterns = [
    path("", StaffListView.as_view(), name="list"),
    path("<int:pk>/deactivate/", StaffDeactivateView.as_view(), name="deactivate"),
]
