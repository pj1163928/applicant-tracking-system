from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.cache import patch_vary_headers
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView
from django.views.generic.detail import SingleObjectMixin

from accounts.mixins import RoleRequiredMixin
from accounts.permissions import (
    AUTHORITY_ASSIGNER_ROLES,
    IN_PROGRESS_VIEWER_ROLES,
    OPENING_MANAGER_ROLES,
    SKILL_RETIRER_ROLES,
    can_decide_closure,
    can_manage_opening_skills,
)
from applications.stages import ACTIVE_STAGES
from config.htmx import is_htmx_partial
from openings.forms import (
    ChangeAuthorityForm,
    CloseOpeningForm,
    ExtendGracePeriodForm,
    GracePeriodForm,
    JobOpeningCreateForm,
    JobOpeningForm,
    ReopenOpeningForm,
    RestoreApplicationsForm,
    SkillAttachForm,
)
from openings.in_progress import STATUS_ORDER, in_progress_openings
from openings.models import JobOpening, Skill
from openings.scopes import ALL, MINE, resolve_scope
from openings.services import (
    INVALID_GRACE_END,
    NOTE_REQUIRED,
    attach_skill,
    cancel_remaining_applications,
    change_authority,
    close_opening,
    detach_skill,
    display_date,
    extend_bounds,
    extend_grace_period,
    plural_days,
    reopen_opening,
    restorable_cancellations,
    restore_applications,
    restore_choices,
    set_grace_period,
)


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

    def get_context_data(self, **kwargs):
        applications = self.object.applications.newest_first().select_related("candidate", "source")
        return (
            super().get_context_data(**kwargs)
            | {"applications": applications}
            | skills_section_context(self.object)
            | closure_context(self.object)
            | restore_context(self.object)
        )


def restore_context(opening: JobOpening) -> dict:
    """What an opening's restore panel shows, once it has been reopened.

    ``restorable_count`` is how many applicants its latest closure cancelled
    who could still be restored; ``restore_pending`` says whether nobody has
    made the restore choice since it reopened (so it is in Needs attention).
    """
    if not opening.is_open:
        return {"restorable_count": 0, "restore_pending": False}
    return {
        "restorable_count": restorable_cancellations(opening).count(),
        "restore_pending": JobOpening.objects.awaiting_restore_choice()
        .filter(pk=opening.pk)
        .exists(),
    }


def closure_context(opening: JobOpening) -> dict:
    """What an opening's closure panel and event history show.

    ``grace_days_left`` is how many days a running grace period has left
    (0 on its end date, before the daily run handles it), or None.
    """
    active = opening.applications.filter(stage__in=ACTIVE_STAGES).select_related("candidate")
    days_left = None
    if opening.grace_period_running:
        days_left = max((opening.grace_period_ends - timezone.localdate()).days, 0)
    return {
        "active_applications": list(
            active.order_by("candidate__last_name", "candidate__first_name")
        ),
        "events": list(opening.events.select_related("by")),
        "grace_days_left": days_left,
    }


def plural(count: int, word: str) -> str:
    """``count`` and ``word``, with an "s" unless there is exactly one."""
    return f"{count} {word}{'' if count == 1 else 's'}"


class InProgressView(RoleRequiredMixin, TemplateView):
    """The Admin in-progress view: closed openings whose applicants are still in progress.

    Admins only (``can_view_in_progress``); everyone else gets 403. Each
    opening shows its status on today's date in the project time zone.
    """

    allowed_roles = IN_PROGRESS_VIEWER_ROLES
    template_name = "openings/in_progress.html"

    def get_context_data(self, **kwargs):
        items = in_progress_openings()
        return super().get_context_data(**kwargs) | {
            "items": items,
            "status_counts": [
                (status, sum(item.status == status for item in items)) for status in STATUS_ORDER
            ],
        }


class OpeningCloseView(RoleRequiredMixin, DetailView):
    """Close an opening, from a confirmation page with an optional note.

    Admins, Recruiters and Hiring Managers only; others get 403 for GET and
    POST. Goes through ``close_opening()``. An opening that is already closed
    sends the user back to it with a message.
    """

    allowed_roles = OPENING_MANAGER_ROLES
    queryset = JobOpening.objects.select_related("designated_authority")
    context_object_name = "opening"
    template_name = "openings/jobopening_close.html"

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not self.object.is_open:
            messages.info(request, f"{self.object.title} is already closed.")
            return redirect(self.object)
        return self.render_to_response(self.get_context_data(form=CloseOpeningForm()))

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | closure_context(self.object)

    def post(self, request, *args, **kwargs):
        self.object = opening = self.get_object()
        form = CloseOpeningForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        try:
            close_opening(opening, by=request.user, note=form.cleaned_data["note"])
        except ValidationError as error:
            messages.info(request, error.messages[0])
            return redirect(opening)
        active = len(closure_context(opening)["active_applications"])
        status = f"Closed {opening.title}. It no longer takes new applications."
        if active:
            authority = opening.designated_authority
            if authority == request.user:
                who = "you decide"
            else:
                who = (
                    f"{authority.get_full_name() or authority.username} has been emailed to decide"
                )
            status += (
                f" {plural(active, 'applicant')} still in progress can keep moving, and "
                f"{who} what happens to them."
            )
        messages.success(request, status)
        return redirect(opening)


class OpeningReopenView(RoleRequiredMixin, DetailView):
    """Reopen a closed opening, from a confirmation page with an optional note.

    Admins, Recruiters and Hiring Managers only (anyone who may close it);
    others get 403 for GET and POST. Goes through ``reopen_opening()``. Someone
    who may decide its closure goes straight on to choosing who to restore;
    anyone else leaves that choice to the designated authority's Needs attention.
    """

    allowed_roles = OPENING_MANAGER_ROLES
    queryset = JobOpening.objects.select_related("designated_authority")
    context_object_name = "opening"
    template_name = "openings/jobopening_reopen.html"

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.is_open:
            messages.info(request, f"{self.object.title} is already open.")
            return redirect(self.object)
        return self.render_to_response(self.get_context_data(form=ReopenOpeningForm()))

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "active_applications": closure_context(self.object)["active_applications"],
            "cancelled_count": restorable_cancellations(self.object).count(),
        }

    def post(self, request, *args, **kwargs):
        self.object = opening = self.get_object()
        form = ReopenOpeningForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        try:
            reopen_opening(opening, by=request.user, note=form.cleaned_data["note"])
        except ValidationError as error:
            messages.info(request, error.messages[0])
            return redirect(opening)
        status = f"Reopened {opening.title}. It takes new applications again."
        cancelled = restorable_cancellations(opening).count()
        if cancelled and can_decide_closure(request.user, opening):
            messages.success(request, f"{status} Now choose who to restore.")
            return redirect("openings:restore", opening.pk)
        if cancelled:
            authority = opening.designated_authority
            status += (
                f" {authority.get_full_name() or authority.username} will see it in Needs "
                f"attention, to choose which of the {plural(cancelled, 'cancelled applicant')} "
                "to restore."
            )
        messages.success(request, status)
        return redirect(opening)


class ClosureDeciderMixin(UserPassesTestMixin):
    """Refuse with 403 unless ``can_decide_closure`` allows the user on this opening.

    For confirmation pages about a closed opening's applicants (cancel now,
    grace periods). Everyone else, Recruiters who aren't its authority
    included, gets 403 for GET and POST. Loads the opening once, as
    ``self.object``, and adds ``closure_context()`` to the page.
    """

    raise_exception = True
    context_object_name = "opening"

    def test_func(self) -> bool:
        self.object = get_object_or_404(
            JobOpening.objects.select_related("designated_authority"), pk=self.kwargs["pk"]
        )
        return can_decide_closure(self.request.user, self.object)

    def get_object(self, queryset=None) -> JobOpening:
        return self.object

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | closure_context(self.object)


class OpeningCancelRemainingView(ClosureDeciderMixin, DetailView):
    """Cancel now: move a closed opening's active applications to Rejected, after confirming.

    Goes through ``cancel_remaining_applications()``, so repeating it (a double
    submission, say) changes nothing. Also works during a grace period; its
    end then has nothing left to cancel.
    """

    template_name = "openings/jobopening_cancel_remaining.html"

    def get(self, request, *args, **kwargs):
        context = self.get_context_data()
        if self.object.is_open:
            messages.info(request, f"{self.object.title} is open, so it has nothing to cancel.")
            return redirect(self.object)
        if not context["active_applications"]:
            messages.info(request, f"No applicants for {self.object.title} are still in progress.")
            return redirect(self.object)
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        opening = self.object
        try:
            rows = cancel_remaining_applications(opening, by=request.user)
        except ValidationError as error:
            messages.error(request, error.messages[0])
            return redirect(opening)
        if rows:
            who = "The candidate has" if len(rows) == 1 else "Each candidate has"
            messages.success(
                request,
                f"Cancelled {plural(len(rows), 'application')} for {opening.title}. "
                f"{who} been emailed that the position closed.",
            )
        else:
            messages.info(
                request, f"Nothing to cancel: no applicants for {opening.title} are in progress."
            )
        return redirect(opening)


class GracePeriodSetView(ClosureDeciderMixin, DetailView):
    """Give a closed opening's remaining applicants a grace period, from a confirmation page.

    Goes through ``set_grace_period()``, which emails each of them once. An
    opening that is open, already has a grace period, or has nobody in
    progress sends the user back to it with a message.
    """

    template_name = "openings/jobopening_grace_period.html"

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(form=GracePeriodForm())
        refusal = self.unavailable(context)
        if refusal:
            messages.info(request, refusal)
            return redirect(self.object)
        return self.render_to_response(context)

    def unavailable(self, context: dict) -> str:
        """Why this page has nothing to offer for the opening, or "" if it does."""
        opening = self.object
        if opening.is_open:
            return f"{opening.title} is open, so its applicants need no grace period."
        if opening.has_grace_period:
            return f"{opening.title} already has a grace period. Extend it instead."
        if not context["active_applications"]:
            return f"No applicants for {opening.title} are still in progress."
        return ""

    def post(self, request, *args, **kwargs):
        opening = self.object
        form = GracePeriodForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        try:
            set_grace_period(
                opening,
                days=form.cleaned_data["days"],
                action=form.cleaned_data["action"],
                by=request.user,
            )
        except ValidationError as error:
            messages.info(request, error.messages[0])
            return redirect(opening)
        count = len(closure_context(opening)["active_applications"])
        who = "The applicant has" if count == 1 else f"All {count} applicants have"
        messages.success(
            request,
            f"Gave the applicants for {opening.title} a grace period of "
            f"{plural_days(form.cleaned_data['days'])}, ending "
            f"{display_date(opening.grace_period_ends)}. {who} been emailed.",
        )
        return redirect(opening)


class GracePeriodExtendView(ClosureDeciderMixin, DetailView):
    """Move a grace period's end date, with a note, from a confirmation page.

    Goes through ``extend_grace_period()``. Works while the grace period runs
    and once a flag-overdue one has ended; candidates get no email, but their
    reminders follow the new date. An opening with nothing to extend sends the
    user back to it with a message.
    """

    template_name = "openings/jobopening_extend_grace_period.html"

    def get(self, request, *args, **kwargs):
        refusal = self.unavailable()
        if refusal:
            messages.info(request, refusal)
            return redirect(self.object)
        return self.render_to_response(self.get_context_data(form=ExtendGracePeriodForm()))

    def unavailable(self) -> str:
        """Why the opening's grace period can't be extended, or "" if it can."""
        opening = self.object
        if opening.is_open or not opening.has_grace_period:
            return f"{opening.title} has no grace period to extend."
        if opening.auto_cancelled:
            return (
                f"The grace period for {opening.title} has ended and its applications were "
                "cancelled, so it can't be extended."
            )
        return ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.object.has_grace_period:
            earliest, latest = extend_bounds(self.object, today=timezone.localdate())
            context |= {"earliest_end": earliest, "latest_end": latest}
            form = context.get("form")
            if form is not None:
                form.fields["ends"].widget.attrs |= {
                    "min": earliest.isoformat(),
                    "max": latest.isoformat(),
                }
        return context

    def post(self, request, *args, **kwargs):
        opening = self.object
        form = ExtendGracePeriodForm(request.POST)
        if form.is_valid():
            try:
                extend_grace_period(
                    opening,
                    ends=form.cleaned_data["ends"],
                    note=form.cleaned_data["note"],
                    by=request.user,
                )
            except ValidationError as error:
                fields = {INVALID_GRACE_END: "ends", NOTE_REQUIRED: "note"}
                if error.code not in fields:
                    messages.info(request, error.messages[0])
                    return redirect(opening)
                form.add_error(fields[error.code], error)
            else:
                messages.success(
                    request,
                    f"Extended the grace period for {opening.title} to "
                    f"{display_date(opening.grace_period_ends)}. Reminders will follow the "
                    "new date.",
                )
                return redirect(opening)
        return self.render_to_response(self.get_context_data(form=form))


class OpeningRestoreView(ClosureDeciderMixin, DetailView):
    """Choose which applicants cancelled at the latest closure go back where they were.

    Users allowed by ``can_decide_closure`` only; everyone else gets 403.
    Archived candidates are listed but can't be ticked. Goes through
    ``restore_applications()``, which emails each restored candidate; "Don't
    restore anyone" records that choice instead. An opening that is closed, or
    has nobody to restore, sends the user back to it with a message.
    """

    template_name = "openings/jobopening_restore.html"

    def get(self, request, *args, **kwargs):
        refusal = self.unavailable()
        if refusal:
            messages.info(request, refusal)
            return redirect(self.object)
        return self.render_page(RestoreApplicationsForm(choices=self.choices))

    def unavailable(self) -> str:
        """Why there is nobody to restore here, or "" if there is. Loads ``self.choices``."""
        opening = self.object
        if not opening.is_open:
            return f"{opening.title} is closed. Reopen it before restoring its applicants."
        self.choices = restore_choices(opening, self.request.user)
        if not self.choices:
            return f"Nobody cancelled when {opening.title} last closed is waiting to be restored."
        return ""

    def render_page(self, form: RestoreApplicationsForm, error: str = ""):
        ticked = {str(value) for value in form["applications"].value() or []}
        return self.render_to_response(
            self.get_context_data(
                form=form,
                choices=self.choices,
                ticked=ticked,
                restore_error=error,
                selectable_count=sum(choice.selectable for choice in self.choices),
            )
        )

    def post(self, request, *args, **kwargs):
        opening = self.object
        refusal = self.unavailable()
        if refusal:
            messages.info(request, refusal)
            return redirect(opening)
        form = RestoreApplicationsForm(request.POST, choices=self.choices)
        if not form.is_valid():
            return self.render_page(form)
        try:
            rows = restore_applications(opening, form.cleaned_data["applications"], by=request.user)
        except ValidationError as error:
            self.choices = restore_choices(opening, request.user)
            form = RestoreApplicationsForm(choices=self.choices)
            return self.render_page(form, error.messages[0])
        if rows:
            who = "The candidate has" if len(rows) == 1 else "Each candidate has"
            messages.success(
                request,
                f"Restored {plural(len(rows), 'applicant')} to {opening.title}, each at their "
                f"stage before the closure. {who} been emailed that the position reopened.",
            )
        else:
            messages.success(
                request, f"Recorded that nobody cancelled from {opening.title} will be restored."
            )
        return redirect(opening)


class OpeningAuthorityView(RoleRequiredMixin, DetailView):
    """Change an opening's designated authority, from a form with an optional note.

    Admins and Recruiters only (``can_reassign_authority``); others get 403 for
    GET and POST. Goes through ``change_authority()``, which writes the
    opening's "authority changed" event and emails the new authority.
    """

    allowed_roles = AUTHORITY_ASSIGNER_ROLES
    queryset = JobOpening.objects.select_related("designated_authority")
    context_object_name = "opening"
    template_name = "openings/jobopening_authority.html"

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return self.render_to_response(
            self.get_context_data(form=ChangeAuthorityForm(opening=self.object))
        )

    def post(self, request, *args, **kwargs):
        self.object = opening = self.get_object()
        form = ChangeAuthorityForm(request.POST, opening=opening)
        if form.is_valid():
            try:
                change_authority(
                    opening,
                    to=form.cleaned_data["authority"],
                    by=request.user,
                    note=form.cleaned_data["note"],
                )
            except ValidationError as error:
                form.add_error("authority", error)
            else:
                authority = opening.designated_authority
                messages.success(
                    request,
                    f"{authority.get_full_name() or authority.username} is now the designated "
                    f"authority for {opening.title}, and has been emailed.",
                )
                return redirect(opening)
        return self.render_to_response(self.get_context_data(form=form))


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


def skills_section_context(
    opening: JobOpening,
    form: SkillAttachForm | None = None,
    status: str = "",
    status_kind: str = "success",
) -> dict:
    """What an opening's Skills section shows: its skills, the add form and its suggestions."""
    return {
        "opening": opening,
        "skills": list(opening.skills.all()),
        "skill_form": form or SkillAttachForm(),
        "skill_suggestions": Skill.objects.active().exclude(openings=opening),
        "skill_status": status,
        "skill_status_kind": status_kind,
    }


class OpeningSkillsMixin(UserPassesTestMixin):
    """Refuse with 403 unless ``can_manage_opening_skills`` allows the user on this opening.

    HTMX requests get the redrawn Skills section; others are redirected to the
    opening with a message.
    """

    raise_exception = True
    http_method_names = ["post"]

    def test_func(self) -> bool:
        self.opening = get_object_or_404(
            JobOpening.objects.select_related("designated_authority"), pk=self.kwargs["pk"]
        )
        return can_manage_opening_skills(self.request.user, self.opening)

    def section(self, status: str, kind: str = "success", form: SkillAttachForm | None = None):
        """Answer with the redrawn Skills section (HTMX), or a message and a redirect."""
        if not is_htmx_partial(self.request):
            level = messages.SUCCESS if kind == "success" else messages.ERROR
            messages.add_message(self.request, level, status)
            return redirect(self.opening)
        context = skills_section_context(self.opening, form, status, kind)
        response = render(self.request, "openings/partials/skills_section.html", context)
        patch_vary_headers(response, ["HX-Request"])
        return response


class OpeningSkillAttachView(OpeningSkillsMixin, View):
    """Add a skill to an opening by name, creating it if it doesn't exist yet.

    Goes through ``attach_skill()``. A name it refuses (blank, retired, already
    listed) comes back as an error under the box.
    """

    def post(self, request, pk):
        form = SkillAttachForm(request.POST)
        if form.is_valid():
            try:
                skill = attach_skill(self.opening, form.cleaned_data["name"], by=request.user)
            except ValidationError as error:
                form.add_error("name", error)
            else:
                return self.section(f"Added {skill.name} to {self.opening.title}.")
        return self.section(form.errors["name"][0], "error", form)


class OpeningSkillDetachView(OpeningSkillsMixin, View):
    """Remove a skill from an opening, through ``detach_skill()``. The skill itself is kept."""

    def post(self, request, pk, skill_pk):
        skill = get_object_or_404(Skill, pk=skill_pk)
        if detach_skill(self.opening, skill, by=request.user):
            return self.section(f"Removed {skill.name} from {self.opening.title}.")
        return self.section(f"{self.opening.title} doesn't list {skill.name}.", "error")


def skill_table_context() -> dict[str, list[Skill]]:
    """The active and retired skills, each with how many openings list it."""
    skills = list(Skill.objects.annotate(opening_count=Count("openings")))
    return {
        "active_skills": [s for s in skills if s.is_active],
        "retired_skills": [s for s in skills if not s.is_active],
    }


class SkillListView(TemplateView):
    """Every skill, active ones first. Everyone may look; only Admins and Hiring Managers
    see the retire and reactivate actions."""

    template_name = "openings/skill_list.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | skill_table_context()


class SkillActivationView(RoleRequiredMixin, SingleObjectMixin, View):
    """Retire a skill, or reactivate it when ``activate`` is True. POST only; never deletes.

    Admins and Hiring Managers only: being an opening's designated authority
    doesn't grant it. HTMX requests get the refreshed skills table back; others
    are redirected to the list with a message.
    """

    allowed_roles = SKILL_RETIRER_ROLES
    model = Skill
    http_method_names = ["post"]
    activate = False

    def post(self, request, *args, **kwargs):
        skill = self.get_object()
        if self.activate:
            skill.reactivate()
            status = f"Reactivated {skill.name}. Openings can add it again."
        else:
            skill.retire()
            status = f"Retired {skill.name}. Openings that list it keep it; others can't add it."
        if is_htmx_partial(request):
            context = skill_table_context() | {"status": status}
            return render(request, "openings/partials/skill_table.html", context)
        messages.success(request, status)
        return redirect("skills:list")
