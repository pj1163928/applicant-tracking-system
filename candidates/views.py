from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.cache import patch_vary_headers
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView
from django.views.generic.detail import SingleObjectMixin

from accounts.mixins import RoleRequiredMixin
from accounts.permissions import (
    CANDIDATE_DELETER_ROLES,
    CANDIDATE_MANAGER_ROLES,
    SOURCE_MANAGER_ROLES,
)
from applications.services import openings_open_to
from candidates.forms import CandidateForm, SourceForm, SourceRenameForm
from candidates.models import Candidate, Source
from candidates.services import (
    archive_candidate,
    archive_refusal,
    delete_candidate,
    deletion_summary,
    unarchive_candidate,
)
from config.htmx import is_htmx_partial


class CandidateListView(ListView):
    """Every candidate, searchable by name or email. HTMX searches get only the results.

    Archived candidates are left out unless ``?archived=1`` ("Show archived").
    """

    model = Candidate
    context_object_name = "candidates"

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.show_archived = request.GET.get("archived") == "1"
        self.listed = (
            Candidate.objects.all() if self.show_archived else Candidate.objects.unarchived()
        )

    def get_queryset(self):
        return self.listed.search(self.request.GET.get("q", ""))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = self.request.GET.get("q", "").strip()
        context["total"] = self.listed.count()
        context["show_archived"] = self.show_archived
        context["archived_count"] = Candidate.objects.filter(is_archived=True).count()
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
            "archive_refusal": None if candidate.is_archived else archive_refusal(candidate),
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


class CandidateArchiveView(RoleRequiredMixin, SingleObjectMixin, View):
    """Archive a candidate, or unarchive them when ``archive`` is False. POST only.

    Admins and Recruiters only. Goes through ``archive_candidate()`` or
    ``unarchive_candidate()``, and returns to the candidate's page with a message,
    including the reason when archiving is refused.
    """

    allowed_roles = CANDIDATE_MANAGER_ROLES
    model = Candidate
    http_method_names = ["post"]
    archive = True

    def post(self, request, *args, **kwargs):
        candidate = self.get_object()
        name = candidate.full_name
        if not self.archive:
            unarchive_candidate(candidate, by=request.user)
            messages.success(request, f"Unarchived {name}. They can apply for openings again.")
            return redirect(candidate)
        try:
            archive_candidate(candidate, by=request.user)
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            messages.success(
                request,
                f"Archived {name}. They're hidden from the candidate list and can't apply for "
                "anything; their applications stay on the boards.",
            )
        return redirect(candidate)


class CandidateDeleteView(RoleRequiredMixin, DetailView):
    """Permanently delete a candidate. Admins only; everyone else gets 403, for GET and POST.

    GET shows a confirmation page listing every application, stage change and
    candidate message that will be destroyed. POST deletes through ``delete_candidate()``.
    """

    allowed_roles = CANDIDATE_DELETER_ROLES
    model = Candidate
    template_name = "candidates/candidate_confirm_delete.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {"summary": deletion_summary(self.object)}

    def post(self, request, *args, **kwargs):
        candidate = self.get_object()
        summary = deletion_summary(candidate)
        name = candidate.full_name
        delete_candidate(candidate, by=request.user)
        applications, changes = len(summary.applications), summary.stage_change_count
        sent = len(summary.messages)
        messages.success(
            request,
            f"Permanently deleted {name}, with {applications} application"
            f"{'' if applications == 1 else 's'}, {changes} stage change"
            f"{'' if changes == 1 else 's'} and {sent} message{'' if sent == 1 else 's'}.",
        )
        return redirect("candidates:list")


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
