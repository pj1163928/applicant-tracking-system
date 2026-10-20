"""Who may take each action: pure permission rules built on ``accounts.roles``.

Views enforce these rules on the server (through ``RoleRequiredMixin`` and its
``allowed_roles``), and templates call the same rules through
``accounts_tags`` to hide actions a user can't take.
"""

from typing import TYPE_CHECKING

from django.contrib.auth.models import Group, User
from django.db.models import Exists, OuterRef, Q, QuerySet

from accounts.roles import HIRING_MANAGER, RECRUITER, AnyUser, has_role

if TYPE_CHECKING:
    from openings.models import JobOpening

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


# Roles that record applications and correct their source. Admins always pass role checks.
APPLICATION_MANAGER_ROLES: tuple[str, ...] = (RECRUITER,)


def can_manage_applications(user: AnyUser) -> bool:
    """Return True if the user may record applications or edit their source.

    That is an Admin or a Recruiter.
    """
    return has_role(user, *APPLICATION_MANAGER_ROLES)


# Roles that move applications between stages. Admins always pass role checks.
# Moving into Offer or Hired also needs ``can_make_offer``.
STAGE_MOVER_ROLES: tuple[str, ...] = (RECRUITER, HIRING_MANAGER)


def can_move_applications(user: AnyUser) -> bool:
    """Return True if the user may move applications between stages at all.

    That is an Admin, a Recruiter or a Hiring Manager. Moves into Offer or
    Hired also need ``can_make_offer()``.
    """
    return has_role(user, *STAGE_MOVER_ROLES)


# Roles that create and edit job openings. Admins always pass role checks.
OPENING_MANAGER_ROLES: tuple[str, ...] = (RECRUITER, HIRING_MANAGER)


def can_manage_openings(user: AnyUser) -> bool:
    """Return True if the user may create or edit job openings.

    That is an Admin, a Recruiter or a Hiring Manager.
    """
    return has_role(user, *OPENING_MANAGER_ROLES)


# Roles that can be an opening's designated authority. Admins always qualify.
AUTHORITY_ROLES: tuple[str, ...] = (RECRUITER, HIRING_MANAGER)


def can_be_designated_authority(user: AnyUser) -> bool:
    """Return True if the user may be made an opening's designated authority.

    That is an active Admin, Recruiter or Hiring Manager. Interviewers, users
    without a role and inactive users never qualify. ``eligible_authorities()``
    returns the same people as a queryset.
    """
    return has_role(user, *AUTHORITY_ROLES)


def eligible_authorities() -> QuerySet[User]:
    """Return the users who may be picked as an opening's designated authority, by name.

    The same rule as ``can_be_designated_authority()``. Forms use it both to
    list the choices and to validate the submitted user, so a hand-made POST
    naming anyone else is refused. Each user appears once, however many
    groups they are in.
    """
    in_authority_role = Exists(Group.objects.filter(user=OuterRef("pk"), name__in=AUTHORITY_ROLES))
    return User.objects.filter(Q(is_superuser=True) | in_authority_role, is_active=True).order_by(
        "first_name", "last_name", "username"
    )


# Roles that may make offers on every opening. Admins always pass role checks.
OFFER_ROLES: tuple[str, ...] = (HIRING_MANAGER,)


def can_make_offer(user: AnyUser, opening: "JobOpening") -> bool:
    """Return True if the user may move ``opening``'s applications into Offer or Hired.

    That is an active Admin, an active Hiring Manager, or the opening's
    designated authority while they are still eligible to be one (active, and
    a Recruiter, Hiring Manager or Admin). Being allowed to move stages, or
    ``is_staff``, never grants it. Closed openings follow the same rule.
    """
    if has_role(user, *OFFER_ROLES):
        return True
    return user.pk == opening.designated_authority_id and can_be_designated_authority(user)
