from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Model, QuerySet
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.views import View
from django.views.generic import CreateView, DetailView, UpdateView

from accounts.mixins import RoleRequiredMixin
from accounts.permissions import APPLICATION_MANAGER_ROLES, STAGE_MOVER_ROLES
from applications.board import board_columns
from applications.forms import ApplicationForm, ApplicationSourceForm, MoveForm
from applications.models import Application
from applications.services import (
    NOTE_REQUIRED,
    move_application,
    move_refusal,
    openings_open_to,
    prefill_source,
    record_application,
)
from applications.stages import (
    BACK,
    CLOSE,
    REOPEN,
    SKIP,
    Stage,
    move_kind,
    prompts_for_note,
    requires_note,
    skipped_stages,
)
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


class PipelineBoardView(DetailView):
    """One opening's pipeline board. Every role may view it; only movers get Move menus."""

    queryset = JobOpening.objects.select_related("designated_authority")
    template_name = "applications/board.html"
    context_object_name = "opening"

    def get_context_data(self, **kwargs):
        columns = board_columns(self.object, self.request.user)
        return super().get_context_data(**kwargs) | {"columns": columns}


NOTE_PROMPTS = {
    BACK: "This moves {name} back. Say why.",
    REOPEN: "This reopens a {stage} application. Say why.",
    CLOSE: "Add a reason if it helps. It's kept in the stage history.",
}


class ApplicationMoveView(RoleRequiredMixin, View):
    """The single endpoint for stage moves, from the Move menu (and, later, drag-and-drop).

    POST ``to_stage`` and ``expected_stage`` (the stage the card showed). A
    move that asks for a note gets the note dialog first; the dialog posts
    again with ``confirmed`` and the note. Every move goes through
    ``move_application()``. HTMX requests get the status message plus the
    affected columns as out-of-band swaps; refusals come back as 400 (or 403
    for permission) with the columns as they really are. Without HTMX, a move
    redirects back to the board.
    """

    allowed_roles = STAGE_MOVER_ROLES
    http_method_names = ["post"]

    def post(self, request, pk):
        self.application = get_object_or_404(
            Application.objects.select_related("candidate", "opening__designated_authority"), pk=pk
        )
        self.opening = self.application.opening
        form = MoveForm(request.POST)
        if not form.is_valid():
            if set(form.errors) == {"note"}:
                return self.ask_for_note(form)
            first_error = next(iter(form.errors.values()))[0]
            return self.refused(
                ValidationError(first_error), form.cleaned_data.get("expected_stage")
            )
        data = form.cleaned_data
        to_stage, shown = data["to_stage"], data["expected_stage"]
        refusal = move_refusal(self.application, to_stage, request.user, expected_stage=shown)
        if refusal is not None:
            return self.refused(refusal, shown)
        if prompts_for_note(self.application.stage, to_stage) and not data["confirmed"]:
            return self.ask_for_note(form)
        from_stage = self.application.stage
        try:
            move_application(
                self.application,
                to_stage,
                by=request.user,
                note=data["note"],
                expected_stage=shown,
            )
        except ValidationError as error:
            if error.code == NOTE_REQUIRED:
                form.add_error("note", error)
                return self.ask_for_note(form)
            return self.refused(error, shown)
        except PermissionDenied as error:
            return self.refused(error, shown)
        name = self.application.candidate.full_name
        message = f"Moved {name} from {Stage(from_stage).label} to {Stage(to_stage).label}."
        if not is_htmx_partial(request):
            messages.success(request, message)
            return redirect("openings:board", self.opening.pk)
        return self.board_update(message, "success", [from_stage, to_stage, shown])

    def refused(self, error: ValidationError | PermissionDenied, shown: str | None):
        """Say why the move wasn't made, and show the columns as they really are."""
        status = 403 if isinstance(error, PermissionDenied) else 400
        message = error.messages[0] if isinstance(error, ValidationError) else str(error)
        if is_htmx_partial(self.request):
            stages = [self.application.stage, shown] if shown else [self.application.stage]
            return self.board_update(message, "error", stages, status=status)
        messages.error(self.request, message)
        columns = board_columns(self.opening, self.request.user)
        context = {"opening": self.opening, "columns": columns}
        return self.respond("applications/board.html", context, status)

    def ask_for_note(self, form: MoveForm):
        """Show the note dialog (or, without HTMX, a page) before making the move."""
        from_stage, to_stage = self.application.stage, form.cleaned_data["to_stage"]
        kind, required = move_kind(from_stage, to_stage), requires_note(from_stage, to_stage)
        if kind == SKIP:
            labels = [stage.label for stage in skipped_stages(from_stage, to_stage)]
            reason = f"This skips {' and '.join(labels)}. Say why it's being expedited."
        else:
            reason = NOTE_PROMPTS[kind].format(
                name=self.application.candidate.full_name,
                stage=Stage(from_stage).label.lower(),
            )
        form.fields["note"].widget.attrs.update(
            {"required": required, "autofocus": True, "placeholder": "Required" if required else ""}
        )
        context = {
            "application": self.application,
            "form": form,
            "to_stage": Stage(to_stage),
            "expected_stage": form.cleaned_data["expected_stage"],
            "requires_note": required,
            "reason": reason,
        }
        if not is_htmx_partial(self.request):
            return self.respond("applications/move_note.html", context)
        response = self.respond("applications/partials/note_dialog.html", context)
        response["HX-Retarget"] = "#dialog-slot"
        response["HX-Reswap"] = "innerHTML"
        return response

    def board_update(self, message: str, level: str, stages: list[str], status: int = 200):
        """The status message, plus the given columns swapped in out of band."""
        columns = board_columns(self.opening, self.request.user, stages)
        context = {"message": message, "level": level, "columns": columns, "opening": self.opening}
        return self.respond("applications/partials/move_result.html", context, status)

    def respond(self, template: str, context: dict, status: int = 200):
        response = render(self.request, template, context, status=status)
        patch_vary_headers(response, ["HX-Request"])
        return response


class ApplicationHistoryView(DetailView):
    """An application's complete stage history, newest first. Every role may view it.

    HTMX requests (from a board card) get it as a dialog; others get a page.
    """

    queryset = Application.objects.select_related(
        "candidate", "opening__designated_authority", "source"
    )
    context_object_name = "application"

    def get_context_data(self, **kwargs):
        changes = self.object.stage_changes.select_related("changed_by").order_by(
            "-changed_at", "-pk"
        )
        return super().get_context_data(**kwargs) | {"changes": changes}

    def get_template_names(self) -> list[str]:
        if is_htmx_partial(self.request):
            return ["applications/partials/history_dialog.html"]
        return ["applications/application_history.html"]

    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        patch_vary_headers(response, ["HX-Request"])
        return response
