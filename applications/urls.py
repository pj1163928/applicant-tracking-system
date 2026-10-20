from django.urls import path

from applications.views import ApplicationCreateView, ApplicationUpdateView

app_name = "applications"

urlpatterns = [
    path("new/", ApplicationCreateView.as_view(), name="create"),
    path("<int:pk>/edit/", ApplicationUpdateView.as_view(), name="update"),
]
