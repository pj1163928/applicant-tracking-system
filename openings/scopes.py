"""Which openings the Openings list shows: the My openings / All toggle.

Ownership only changes the default filter and labels, never what anyone can
see: every opening is always reachable through ``ALL`` and by its URL.
"""

from typing import Literal

from accounts.roles import HIRING_MANAGER, AnyUser, role_label

type Scope = Literal["mine", "all"]

MINE: Scope = "mine"
ALL: Scope = "all"
SCOPES: tuple[Scope, ...] = (MINE, ALL)


def default_scope(user: AnyUser) -> Scope:
    """Return the scope the Openings list starts on for ``user``.

    Hiring Managers start on ``MINE``; everyone else, including Admins and
    users without a role, starts on ``ALL``. The role is the one ``role_label``
    shows, so an Admin counts as an Admin even if they are also in the
    Hiring Manager group.
    """
    return MINE if role_label(user) == HIRING_MANAGER else ALL


def resolve_scope(user: AnyUser, requested: str | None) -> Scope:
    """Return the requested scope if it is valid, otherwise the user's default."""
    if requested in SCOPES:
        return requested
    return default_scope(user)
