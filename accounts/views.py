from django.contrib import messages
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.shortcuts import redirect
from django.views.generic import DetailView, ListView, TemplateView

from accounts import dashboard
from accounts.forms import DeactivateStaffForm
from accounts.mixins import RoleRequiredMixin
from accounts.permissions import STAFF_MANAGER_ROLES, can_be_designated_authority
from accounts.roles import can_make_changes
from accounts.services import deactivate_staff
from openings.services import display_name
from openings.views import plural


class HomeView(TemplateView):
    """Landing page after login: who is signed in, and what is theirs to look at or act on.

    Its four lists sit in a two-by-two grid (Needs attention and Your openings
    on top, Applicants on your openings and Your recent work below), each
    folded to ``dashboard.FOLD_AT`` rows. Sections that can't apply to the
    user are left out: someone who can't be a
    designated authority has no openings or applicants of their own, and
    someone who can't make changes has no recent work.
    """

    template_name = "accounts/home.html"

    def get_context_data(self, **kwargs):
        user = self.request.user
        context = super().get_context_data(**kwargs) | {
            "stats": dashboard.home_stats(user),
            "pipeline": dashboard.pipeline_snapshot(),
            "may_own_openings": can_be_designated_authority(user),
            "may_change": can_make_changes(user),
        }
        if context["may_own_openings"]:
            context |= {
                "my_attention": dashboard.Fold(dashboard.your_attention(user)),
                "my_openings": dashboard.Fold(dashboard.your_openings(user)),
                "my_applicants": dashboard.Fold(dashboard.applicants_on_your_openings(user)),
            }
        if context["may_change"]:
            context["my_work"] = dashboard.Fold(dashboard.recent_work(user))
        return context


class StaffListView(RoleRequiredMixin, ListView):
    """Every staff account, active ones first, with how many openings each is responsible for.

    Admins only (``can_manage_staff``); everyone else gets 403.
    """

    allowed_roles = STAFF_MANAGER_ROLES
    context_object_name = "staff"
    template_name = "accounts/staff_list.html"

    def get_queryset(self):
        return (
            User.objects.annotate(opening_count=Count("authority_openings"))
            .prefetch_related("groups")
            .order_by("-is_active", "first_name", "last_name", "username")
        )


class StaffDeactivateView(RoleRequiredMixin, DetailView):
    """Deactivate a departing staff member, picking a new authority for each of their openings.

    Admins only; everyone else gets 403 for GET and POST. Goes through
    ``deactivate_staff()``, which hands every opening over and deactivates the
    account in one transaction, or changes nothing.
    """

    allowed_roles = STAFF_MANAGER_ROLES
    model = User
    context_object_name = "person"
    template_name = "accounts/staff_deactivate.html"

    def unavailable(self) -> str:
        """Why this account can't be deactivated here, or "" if it can."""
        person = self.object
        if person == self.request.user:
            return "You can't deactivate your own account."
        if not person.is_active:
            return f"{display_name(person)} is already deactivated."
        return ""

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        refusal = self.unavailable()
        if refusal:
            messages.info(request, refusal)
            return redirect("staff:list")
        return self.render_to_response(
            self.get_context_data(form=DeactivateStaffForm(user=self.object))
        )

    def post(self, request, *args, **kwargs):
        self.object = person = self.get_object()
        form = DeactivateStaffForm(request.POST, user=person)
        if form.is_valid():
            try:
                events = deactivate_staff(person, form.reassignments(), by=request.user)
            except ValidationError as error:
                form.add_error(None, error)
            else:
                if events:
                    status = (
                        f"Deactivated {display_name(person)}. {plural(len(events), 'opening')} "
                        "handed over, and each new authority has been emailed."
                    )
                else:
                    status = (
                        f"Deactivated {display_name(person)}. They had no openings to hand over."
                    )
                messages.success(request, status)
                return redirect("staff:list")
        return self.render_to_response(self.get_context_data(form=form))
