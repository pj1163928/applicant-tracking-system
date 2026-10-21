"""What the Needs attention panel lists: decisions waiting on the signed-in user.

For now that is closed openings whose applicants are still in progress and
which have no grace period running: closures awaiting a decision, and overdue
ones (a flag-overdue grace period that has ended). Each item is one the user may decide, by
``accounts.permissions.can_decide_closure``; the openings they are the
designated authority of come first.
"""

from dataclasses import dataclass

from accounts.permissions import (
    can_be_designated_authority,
    can_decide_closure,
    is_eligible_authority_of,
)
from accounts.roles import AnyUser
from openings.models import JobOpening, OpeningEvent
from openings.services import latest_closure


@dataclass(frozen=True)
class AttentionItem:
    """One closed opening waiting for a decision about its remaining applicants.

    ``opening`` carries ``active_count``; ``closed`` is its latest "closed"
    event, if one was recorded; ``assigned_to_you`` is True when the user is
    its designated authority.
    """

    opening: JobOpening
    closed: OpeningEvent | None
    assigned_to_you: bool


def closures_awaiting_decision(user: AnyUser) -> list[AttentionItem]:
    """Return the closures awaiting a decision that ``user`` may make, theirs first, then by title.

    Admins and Hiring Managers may decide for every opening, so they see every
    one; a designated authority sees their own; everyone else sees none.
    """
    openings = (
        JobOpening.objects.awaiting_closure_decision()
        .select_related("designated_authority")
        .order_by("title", "pk")
    )
    items = [
        AttentionItem(
            opening=opening,
            closed=latest_closure(opening),
            assigned_to_you=is_eligible_authority_of(user, opening),
        )
        for opening in openings
        if can_decide_closure(user, opening)
    ]
    return sorted(items, key=lambda item: not item.assigned_to_you)


def attention_count(user: AnyUser) -> int:
    """Return how many closures await a decision from ``user`` as designated authority.

    Overdue openings count too; ones whose grace period is still running don't.

    The navigation badge shows this. Openings that Admins and Hiring Managers
    could decide for others aren't counted, so the badge means "yours".
    """
    if not can_be_designated_authority(user):
        return 0
    return JobOpening.objects.awaiting_closure_decision().filter(designated_authority=user).count()
