"""Who may take each action: pure permission rules built on ``accounts.roles``.

Views enforce these rules on the server (through ``RoleRequiredMixin`` and its
``allowed_roles``), and templates call the same rules through
``accounts_tags`` to hide actions a user can't take.
"""

from accounts.roles import RECRUITER, AnyUser, has_role

# Roles that add and edit candidates. Admins always pass role checks.
CANDIDATE_MANAGER_ROLES: tuple[str, ...] = (RECRUITER,)


def can_manage_candidates(user: AnyUser) -> bool:
    """Return True if the user may add or edit candidates: an Admin or a Recruiter."""
    return has_role(user, *CANDIDATE_MANAGER_ROLES)


# Roles that add, rename, retire and reactivate sources. Admins always pass role checks.
SOURCE_MANAGER_ROLES: tuple[str, ...] = (RECRUITER,)


def can_manage_sources(user: AnyUser) -> bool:
    """Return True if the user may add, rename, retire or reactivate sources.

    That is an Admin or a Recruiter.
    """
    return has_role(user, *SOURCE_MANAGER_ROLES)
