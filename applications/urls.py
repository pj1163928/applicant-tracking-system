from django.urls import path

from applications.views import (
    ApplicationCreateView,
    ApplicationHistoryView,
    ApplicationMoveView,
    ApplicationUpdateView,
)

app_name = "applications"

urlpatterns = [
    path("new/", ApplicationCreateView.as_view(), name="create"),
    path("<int:pk>/edit/", ApplicationUpdateView.as_view(), name="update"),
    path("<int:pk>/move/", ApplicationMoveView.as_view(), name="move"),
    path("<int:pk>/history/", ApplicationHistoryView.as_view(), name="history"),
]
