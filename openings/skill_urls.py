"""Skill URLs, mounted at /skills/. Skills live in the openings app, in their own namespace."""

from django.urls import path

from openings.views import SkillActivationView, SkillListView

app_name = "skills"

urlpatterns = [
    path("", SkillListView.as_view(), name="list"),
    path("<int:pk>/retire/", SkillActivationView.as_view(activate=False), name="retire"),
    path("<int:pk>/reactivate/", SkillActivationView.as_view(activate=True), name="reactivate"),
]
