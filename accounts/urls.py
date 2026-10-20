from django.contrib.auth import views as auth_views
from django.urls import path

from accounts.views import HomeView

app_name = "accounts"

# Staff accounts are created by an Admin. There is deliberately no sign-up URL.
urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(redirect_authenticated_user=True),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
]
