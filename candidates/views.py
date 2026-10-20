from django.contrib.messages.views import SuccessMessageMixin
from django.utils.cache import patch_vary_headers
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from accounts.mixins import RoleRequiredMixin
from accounts.permissions import CANDIDATE_MANAGER_ROLES
from candidates.forms import CandidateForm
from candidates.models import Candidate


def is_htmx_partial(request) -> bool:
    """True for an HTMX request that wants a fragment, not a history restore of the full page."""
    return (
        request.headers.get("HX-Request") == "true"
        and request.headers.get("HX-History-Restore-Request") != "true"
    )


class CandidateListView(ListView):
    """Every candidate, searchable by name or email. HTMX searches get only the results."""

    model = Candidate
    context_object_name = "candidates"

    def get_queryset(self):
        return Candidate.objects.search(self.request.GET.get("q", ""))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = self.request.GET.get("q", "").strip()
        context["total"] = Candidate.objects.count()
        return context

    def get_template_names(self) -> list[str]:
        if is_htmx_partial(self.request):
            return ["candidates/partials/results.html"]
        return ["candidates/candidate_list.html"]

    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        patch_vary_headers(response, ["HX-Request"])
        return response


class CandidateDetailView(DetailView):
    """A candidate's contact details and (from Phase 5) their applications."""

    model = Candidate


class CandidateCreateView(RoleRequiredMixin, SuccessMessageMixin, CreateView):
    """Add a candidate. Admins and Recruiters only; everyone else gets 403."""

    allowed_roles = CANDIDATE_MANAGER_ROLES
    model = Candidate
    form_class = CandidateForm
    success_message = "Added %(first_name)s %(last_name)s."


class CandidateUpdateView(RoleRequiredMixin, SuccessMessageMixin, UpdateView):
    """Edit a candidate's details. Admins and Recruiters only; everyone else gets 403."""

    allowed_roles = CANDIDATE_MANAGER_ROLES
    model = Candidate
    form_class = CandidateForm
    success_message = "Saved changes to %(first_name)s %(last_name)s."
