from django.urls import path

from notifications.views import AttentionView

app_name = "notifications"

urlpatterns = [
    path("", AttentionView.as_view(), name="attention"),
]
