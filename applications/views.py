from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.db.models import Model, QuerySet
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.views.generic import CreateView, UpdateView

from accounts.mixins import RoleRequiredMixin
from accounts.permissions import APPLICATION_MANAGER_ROLES
from applications.forms import ApplicationForm, ApplicationSourceForm
from applications.models import Application
from applications.services import openings_open_to, prefill_source, record_application
from candidates.models import Candidate
from config.htmx import is_htmx_partial
from openings.models import JobOpening

SOURCE_FIELDS_TEMPLATE = "applications/partials/source_fields.html"


def object_from_param(queryset: QuerySet, value: str | None) -> Model | None:
    """The record a query-string pk names, or None if it is missing, malformed or unknown."""
    if not value or not value.isdigit():
        return None
    return queryset.filter(pk=value).first()


class SourceFieldsMixin:
    """HTMX GETs get just the source fields back, so "referred by" follows the chosen source."""

    def get_form_kwargs(self):
        return super().get_form_kwargs() | {"refresh_url": self.request.path}

    def get(self, request, *args, **kwargs):
        if not is_htmx_partial(request):
            response = super().get(request, *args, **kwargs)
        else:
            self.object = self.get_object() if self.pk_url_kwarg in self.kwargs else None
            response = render(request, SOURCE_FIELDS_TEMPLATE, {"form": self.get_form()})
        patch_vary_headers(response, ["HX-Request"])
        return response


class ApplicationCreateView(RoleRequiredMixin, SourceFieldsMixin, CreateView):
    """Record that a candidate applied for an open opening. Admins and Recruiters only.

    Started from a candidate's page (``?candidate=<pk>``) or an open opening's
    page (``?opening=<pk>``). The source is pre-filled from the candidate's most
    recent application. Saving goes through ``record_application()``.
    """

    allowed_roles = APPLICATION_MANAGER_ROLES
    model = Application
    form_class = ApplicationForm

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.preset_candidate = object_from_param(
            Candidate.objects.all(), request.GET.get("candidate")
        )
        self.preset_opening = object_from_param(
            JobOpening.objects.all(), request.GET.get("opening")
        )

    def get(self, request, *args, **kwargs):
        # The pages hide the action when there's nowhere to apply; refuse here too.
        # HTMX refreshes of the source fields are left alone: the form reports those.
        opening, candidate = self.preset_opening, self.preset_candidate
        if is_htmx_partial(request):
            return super().get(request, *args, **kwargs)
        if opening is not None and not opening.is_open:
            messages.error(
                request, f"{opening.title} is closed, so it can't take new applications."
            )
            return redirect(opening)
        if candidate is not None and not openings_open_to(candidate).exists():
            messages.error(
                request, f"There are no open openings {candidate.full_name} hasn't applied for."
            )
            return redirect(candidate)
        return super().get(request, *args, **kwargs)

    def get_initial(self):
        params = self.request.GET
        initial = {name: params[name] for name in ("source", "referred_by") if params.get(name)}
        if self.preset_candidate is not None:
            initial["candidate"] = self.preset_candidate.pk
        if self.preset_opening is not None:
            initial["opening"] = self.preset_opening.pk
        # Pre-fill on first load, and again whenever the candidate is changed.
        picking_candidate = self.request.headers.get("HX-Trigger-Name") == "candidate"
        if self.preset_candidate is not None and ("source" not in initial or picking_candidate):
            source = prefill_source(self.preset_candidate)
            if source is not None:
                initial["source"] = source.pk
        return initial

    def form_valid(self, form):
        data = form.cleaned_data
        try:
            self.object = record_application(
                candidate=data["candidate"],
                opening=data["opening"],
                source=data["source"],
                referred_by=data["referred_by"],
                by=self.request.user,
            )
        except ValidationError as error:
            # Something changed since the form was checked, such as the opening closing.
            form.add_error(None, error)
            return self.form_invalid(form)
        messages.success(
            self.request,
            f"Recorded {self.object.candidate.full_name}'s application for "
            f"{self.object.opening.title}, at Applied.",
        )
        return redirect(self.get_success_url())

    def started_from_opening(self) -> bool:
        return self.preset_opening is not None and self.preset_candidate is None

    def get_success_url(self) -> str:
        if self.started_from_opening():
            return self.object.opening.get_absolute_url()
        return self.object.candidate.get_absolute_url()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.started_from_opening():
            back = (self.preset_opening.get_absolute_url(), f"Back to {self.preset_opening.title}")
        elif self.preset_candidate is not None:
            back = (
                self.preset_candidate.get_absolute_url(),
                f"Back to {self.preset_candidate.full_name}",
            )
        else:
            back = (reverse("candidates:list"), "All candidates")
        return context | {"back_url": back[0], "back_label": back[1]}


class ApplicationUpdateView(RoleRequiredMixin, SourceFieldsMixin, SuccessMessageMixin, UpdateView):
    """Correct an application's source and "referred by". Admins and Recruiters only.

    A retired source the application already has stays on the form. Opened
    from an opening's page with ``?from=opening``, it returns there.
    """

    allowed_roles = APPLICATION_MANAGER_ROLES
    queryset = Application.objects.select_related("candidate", "opening", "source")
    form_class = ApplicationSourceForm
    context_object_name = "application"

    def get_initial(self):
        params = self.request.GET
        return {name: params[name] for name in ("source", "referred_by") if name in params}

    def get_success_message(self, cleaned_data) -> str:
        return (
            f"Saved the source of {self.object.candidate.full_name}'s application "
            f"for {self.object.opening.title}."
        )

    def back_to(self) -> Model:
        return (
            self.object.opening
            if self.request.GET.get("from") == "opening"
            else self.object.candidate
        )

    def get_success_url(self) -> str:
        return self.back_to().get_absolute_url()

    def get_context_data(self, **kwargs):
        back = self.back_to()
        return super().get_context_data(**kwargs) | {
            "back_url": back.get_absolute_url(),
            "back_label": f"Back to {back}",
        }
