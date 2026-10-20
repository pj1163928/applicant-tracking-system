"""Test-only URLs: views that exercise RoleRequiredMixin without a real feature."""

from django.http import HttpResponse
from django.urls import include, path
from django.views import View

from accounts.mixins import RoleRequiredMixin
from accounts.roles import RECRUITER


class ChangeView(RoleRequiredMixin, View):
    def get(self, request):
        return HttpResponse("form")

    def post(self, request):
        return HttpResponse("saved")


class RecruiterOnlyView(ChangeView):
    allowed_roles = (RECRUITER,)


urlpatterns = [
    path("", include("accounts.urls")),
    path("change/", ChangeView.as_view(), name="change"),
    path("recruiter-only/", RecruiterOnlyView.as_view(), name="recruiter-only"),
]
