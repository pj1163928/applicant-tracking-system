"""View mixins that enforce the role checks in ``accounts.roles`` on the server."""

from django.contrib.auth.mixins import UserPassesTestMixin

from accounts.roles import EDITOR_ROLES, has_role


class RoleRequiredMixin(UserPassesTestMixin):
    """Refuse the view with 403 unless the user is an Admin or holds an allowed role.

    The default ``allowed_roles`` refuses Interviewers and users without a role,
    so any view that changes data can use this mixin as-is. Narrow it per view,
    for example ``allowed_roles = (RECRUITER,)`` for candidate editing.
    Anonymous users never reach it: ``LoginRequiredMiddleware`` redirects them first.
    """

    allowed_roles: tuple[str, ...] = EDITOR_ROLES
    raise_exception = True

    def test_func(self) -> bool:
        return has_role(self.request.user, *self.allowed_roles)
