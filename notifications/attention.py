"""What the Needs attention panel lists: decisions waiting on the signed-in user.

Two kinds: closed openings whose applicants are still in progress and which
have no grace period running (closures awaiting a decision, and overdue ones,
a flag-overdue grace period that has ended), and reopened openings where
someone must choose which cancelled applicants to restore. Each item is one
the user may decide, by ``accounts.permissions.can_decide_closure``; the
openings they are the designated authority of come first.
"""

from dataclasses import dataclass

from accounts.permissions import (
    CLOSURE_DECIDER_ROLES,
    can_be_designated_authority,
    can_decide_closure,
    is_eligible_authority_of,
)
from accounts.roles import AnyUser, has_role
from openings.models import JobOpening, OpeningEvent
from openings.services import latest_closure, latest_reopening


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

    kind = "closure"


@dataclass(frozen=True)
class RestoreItem:
    """One reopened opening waiting for someone to choose which cancelled applicants to restore.

    ``opening`` carries ``restorable_count``; ``reopened`` is its latest
    "reopened" event; ``assigned_to_you`` is True when the user is its
    designated authority.
    """

    opening: JobOpening
    reopened: OpeningEvent | None
    assigned_to_you: bool

    kind = "restore"


def restores_awaiting_choice(user: AnyUser) -> list[RestoreItem]:
    """Return the restore choices waiting that ``user`` may make, theirs first, then by title.

    The same people as ``closures_awaiting_decision``: Admins and Hiring
    Managers see every one, a designated authority sees their own.
    """
    openings = (
        JobOpening.objects.awaiting_restore_choice()
        .select_related("designated_authority")
        .order_by("title", "pk")
    )
    items = [
        RestoreItem(
            opening=opening,
            reopened=latest_reopening(opening),
            assigned_to_you=is_eligible_authority_of(user, opening),
        )
        for opening in openings
        if can_decide_closure(user, opening)
    ]
    return sorted(items, key=lambda item: not item.assigned_to_you)


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
    """Return how many decisions await ``user`` as designated authority.

    That is closures awaiting a decision (overdue ones too; ones whose grace
    period is still running don't count) plus reopened openings waiting for a
    restore choice. The navigation badge shows this. Openings that Admins and
    Hiring Managers could decide for others aren't counted, so the badge means "yours".
    """
    if not can_be_designated_authority(user):
        return 0
    return (
        JobOpening.objects.awaiting_closure_decision().filter(designated_authority=user).count()
        + JobOpening.objects.awaiting_restore_choice().filter(designated_authority=user).count()
    )


@dataclass(frozen=True)
class AttentionSummary:
    """How many decisions await a user, split as the panel groups them.

    ``yours`` is the navigation badge's number (``attention_count``);
    ``others`` are the ones an Admin or Hiring Manager may decide for someone
    else, and ``decides_for_others`` says whether the user may do that at all.
    """

    yours: int
    others: int
    decides_for_others: bool

    @property
    def total(self) -> int:
        return self.yours + self.others


def attention_summary(user: AnyUser) -> AttentionSummary:
    """Return the counts behind the navigation's Needs attention badge and its breakdown.

    The same split as ``closures_awaiting_decision`` and
    ``restores_awaiting_choice`` (``assigned_to_you`` or not), counted in the
    database instead of listing every opening.
    """
    decides_for_others = has_role(user, *CLOSURE_DECIDER_ROLES)
    others = 0
    if decides_for_others:
        others = (
            JobOpening.objects.awaiting_closure_decision()
            .exclude(designated_authority=user)
            .count()
            + JobOpening.objects.awaiting_restore_choice()
            .exclude(designated_authority=user)
            .count()
        )
    return AttentionSummary(attention_count(user), others, decides_for_others)
