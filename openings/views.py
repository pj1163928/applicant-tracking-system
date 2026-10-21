from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.cache import patch_vary_headers
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView
from django.views.generic.detail import SingleObjectMixin

from accounts.mixins import RoleRequiredMixin
from accounts.permissions import (
    OPENING_MANAGER_ROLES,
    SKILL_RETIRER_ROLES,
    can_manage_opening_skills,
)
from config.htmx import is_htmx_partial
from openings.forms import JobOpeningCreateForm, JobOpeningForm, SkillAttachForm
from openings.models import JobOpening, Skill
from openings.scopes import ALL, MINE, resolve_scope
from openings.services import attach_skill, detach_skill


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
        )


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
