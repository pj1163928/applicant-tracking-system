from django.views.generic import TemplateView


class HomeView(TemplateView):
    """Landing page after login: a welcome showing who is signed in and their role."""

    template_name = "accounts/home.html"
