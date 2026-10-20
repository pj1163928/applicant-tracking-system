from django.contrib.messages.views import SuccessMessageMixin
from django.utils.cache import patch_vary_headers
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from accounts.mixins import RoleRequiredMixin
from accounts.permissions import OPENING_MANAGER_ROLES
from config.htmx import is_htmx_partial
from openings.forms import JobOpeningCreateForm, JobOpeningForm
from openings.models import JobOpening
from openings.scopes import ALL, MINE, resolve_scope


class OpeningListView(ListView):
    """Every opening, with the My openings / All toggle. HTMX toggles get only the results."""

    context_object_name = "openings"

    def get_queryset(self):
        self.scope = resolve_scope(self.request.user, self.request.GET.get("show"))
        return (
            JobOpening.objects.in_scope(self.scope, self.request.user)
            .open_first()
            .select_related("designated_authority")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        mine_count = JobOpening.objects.in_scope(MINE, self.request.user).count()
        all_count = JobOpening.objects.count()
        return context | {
            "scope": self.scope,
            "MINE": MINE,
            "ALL": ALL,
            "all_count": all_count,
            "tabs": [(MINE, "My openings", mine_count), (ALL, "All", all_count)],
        }

    def get_template_names(self) -> list[str]:
        if is_htmx_partial(self.request):
            return ["openings/partials/results.html"]
        return ["openings/jobopening_list.html"]

    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        patch_vary_headers(response, ["HX-Request"])
        return response


class OpeningDetailView(DetailView):
    """An opening's details and designated authority. Every role may view every opening."""

    queryset = JobOpening.objects.select_related("designated_authority")
    context_object_name = "opening"


class OpeningCreateView(RoleRequiredMixin, SuccessMessageMixin, CreateView):
    """Create an opening. Admins, Recruiters and Hiring Managers only; others get 403."""

    allowed_roles = OPENING_MANAGER_ROLES
    model = JobOpening
    form_class = JobOpeningCreateForm
    success_message = "Created %(title)s."


class OpeningUpdateView(RoleRequiredMixin, SuccessMessageMixin, UpdateView):
    """Edit an opening's details. Admins, Recruiters and Hiring Managers only; others get 403."""

    allowed_roles = OPENING_MANAGER_ROLES
    queryset = JobOpening.objects.select_related("designated_authority")
    form_class = JobOpeningForm
    context_object_name = "opening"
    success_message = "Saved changes to %(title)s."
