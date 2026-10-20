"""Staff roles and the pure role checks that every permission rule builds on.

Roles are Django Groups (created by migration ``0001_create_role_groups``);
Admin is ``is_superuser``. Views, mixins and templates call these functions
instead of inspecting groups themselves.
"""

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

RECRUITER = "Recruiter"
HIRING_MANAGER = "Hiring Manager"
INTERVIEWER = "Interviewer"

ROLE_GROUPS: tuple[str, ...] = (RECRUITER, HIRING_MANAGER, INTERVIEWER)

# Roles that may change data. Interviewers are view-only.
EDITOR_ROLES: tuple[str, ...] = (RECRUITER, HIRING_MANAGER)

type AnyUser = AbstractBaseUser | AnonymousUser


def is_admin(user: AnyUser) -> bool:
    """Return True if the user is an active Admin (a superuser)."""
    return bool(user.is_authenticated and user.is_active and user.is_superuser)


def has_role(user: AnyUser, *roles: str) -> bool:
    """Return True if the user is an Admin or belongs to any of ``roles``.

    Admins pass every role check. Anonymous and inactive users never pass.
    """
    if not (user.is_authenticated and user.is_active):
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=roles).exists()


def can_make_changes(user: AnyUser) -> bool:
    """Return True if the user may change data at all.

    Admins, Recruiters and Hiring Managers may; Interviewers and users without
    a role may not. Individual actions narrow this further in later phases.
    """
    return has_role(user, *EDITOR_ROLES)


def role_label(user: AnyUser) -> str:
    """Return the user's role for display: "Admin", a group name, or "No role"."""
    if not user.is_authenticated:
        return ""
    if user.is_superuser:
        return "Admin"
    names = set(user.groups.filter(name__in=ROLE_GROUPS).values_list("name", flat=True))
    for role in ROLE_GROUPS:
        if role in names:
            return role
    return "No role"
