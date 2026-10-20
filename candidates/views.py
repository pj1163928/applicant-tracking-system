from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.cache import patch_vary_headers
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView
from django.views.generic.detail import SingleObjectMixin

from accounts.mixins import RoleRequiredMixin
from accounts.permissions import CANDIDATE_MANAGER_ROLES, SOURCE_MANAGER_ROLES
from applications.services import openings_open_to
from candidates.forms import CandidateForm, SourceForm, SourceRenameForm
from candidates.models import Candidate, Source
from config.htmx import is_htmx_partial


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
    """A candidate's contact details and their applications, newest first."""

    model = Candidate

    def get_context_data(self, **kwargs):
        candidate = self.object
        return super().get_context_data(**kwargs) | {
            "applications": candidate.applications.newest_first().select_related(
                "opening", "source"
            ),
            "has_openings_to_apply": openings_open_to(candidate).exists(),
        }


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


def source_table_context() -> dict[str, list[Source]]:
    """The active and retired sources, as the sources table shows them."""
    sources = list(Source.objects.all())
    return {
        "active_sources": [s for s in sources if s.is_active],
        "retired_sources": [s for s in sources if not s.is_active],
    }


class SourceListView(TemplateView):
    """Every source, active ones first. Everyone may look; only managers see the actions."""

    template_name = "candidates/source_list.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | source_table_context()


class SourceCreateView(RoleRequiredMixin, SuccessMessageMixin, CreateView):
    """Add a source. Admins and Recruiters only; everyone else gets 403."""

    allowed_roles = SOURCE_MANAGER_ROLES
    model = Source
    form_class = SourceForm
    success_url = reverse_lazy("sources:list")
    success_message = "Added %(name)s."


class SourceRenameView(RoleRequiredMixin, SuccessMessageMixin, UpdateView):
    """Rename a source. Admins and Recruiters only; everyone else gets 403."""

    allowed_roles = SOURCE_MANAGER_ROLES
    model = Source
    form_class = SourceRenameForm
    success_url = reverse_lazy("sources:list")
    success_message = "Renamed the source to %(name)s."

    def get_object(self, queryset=None) -> Source:
        source = super().get_object(queryset)
        # A failed rename copies the typed name onto the object; keep the saved one for headings.
        self.saved_name = source.name
        return source

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {"saved_name": self.saved_name}


class SourceActivationView(RoleRequiredMixin, SingleObjectMixin, View):
    """Retire a source, or reactivate it when ``activate`` is True. POST only; never deletes.

    HTMX requests get the refreshed sources table back; others are redirected
    to the list with a message.
    """

    allowed_roles = SOURCE_MANAGER_ROLES
    model = Source
    http_method_names = ["post"]
    activate = False

    def post(self, request, *args, **kwargs):
        source = self.get_object()
        if self.activate:
            source.reactivate()
            status = f"Reactivated {source.name}. New applications can pick it again."
        else:
            source.retire()
            status = f"Retired {source.name}. Old applications keep it; new ones can't pick it."
        if is_htmx_partial(request):
            context = source_table_context() | {"status": status}
            return render(request, "candidates/partials/source_table.html", context)
        messages.success(request, status)
        return redirect("sources:list")
