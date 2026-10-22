"""What the Admin in-progress view lists: closed openings whose applicants are still in progress.

Each opening's status (Awaiting decision, In grace period or Overdue) comes
from the pure ``openings.grace.closure_status`` on the day passed in, so a
late or missed ``process_grace_periods`` run still shows as Overdue.
"""

from dataclasses import dataclass
from datetime import date

from django.utils import timezone

from openings.grace import ClosureStatus, closure_status
from openings.models import JobOpening, OpeningEvent
from openings.services import latest_closure

# The order the view lists statuses in: the most urgent first.
STATUS_ORDER: tuple[ClosureStatus, ...] = (
    ClosureStatus.OVERDUE,
    ClosureStatus.AWAITING_DECISION,
    ClosureStatus.IN_GRACE_PERIOD,
)


@dataclass(frozen=True)
class InProgressCounts:
    """How many closed openings with applicants in progress have each status.

    The navigation badge shows ``to_act_on``: Overdue and Awaiting decision.
    In grace period is left out, since nobody needs to act until it ends.
    """

    overdue: int
    awaiting_decision: int
    in_grace_period: int

    @property
    def to_act_on(self) -> int:
        return self.overdue + self.awaiting_decision

    @property
    def total(self) -> int:
        return self.to_act_on + self.in_grace_period


@dataclass(frozen=True)
class InProgressItem:
    """One closed opening with applicants still in progress.

    ``opening`` carries ``active_count``; ``closed`` is its latest "closed"
    event, if one was recorded; ``days_left`` is how many days a grace period
    in progress has left (None for the other statuses).
    """

    opening: JobOpening
    status: ClosureStatus
    closed: OpeningEvent | None
    days_left: int | None


def in_progress_openings(*, today: date | None = None) -> list[InProgressItem]:
    """Return every closed opening with an active application, most urgent status first.

    ``today`` defaults to ``timezone.localdate()``. Within a status, openings
    are ordered by title. An opening with nobody in progress is left out.
    """
    today = today or timezone.localdate()
    openings = (
        JobOpening.objects.closed_with_active_applications()
        .select_related("designated_authority")
        .order_by("title", "pk")
    )
    items = []
    for opening in openings:
        status = opening_status(opening, today=today)
        days_left = None
        if status == ClosureStatus.IN_GRACE_PERIOD:
            days_left = (opening.grace_period_ends - today).days
        items.append(InProgressItem(opening, status, latest_closure(opening), days_left))
    return sorted(items, key=lambda item: STATUS_ORDER.index(item.status))


def opening_status(opening: JobOpening, *, today: date) -> ClosureStatus:
    """Return ``opening``'s status on ``today``, from its stored grace-period fields."""
    return closure_status(
        ends=opening.grace_period_ends,
        action=opening.grace_expiry_action,
        expired_on=opening.grace_expired_on,
        today=today,
    )


def in_progress_counts(*, today: date | None = None) -> InProgressCounts:
    """Count the openings ``in_progress_openings`` would list, by status, in one query.

    ``today`` defaults to ``timezone.localdate()``.
    """
    today = today or timezone.localdate()
    statuses = [
        opening_status(opening, today=today)
        for opening in JobOpening.objects.closed_with_active_applications().only(
            "grace_period_ends", "grace_expiry_action", "grace_expired_on"
        )
    ]
    return InProgressCounts(
        overdue=statuses.count(ClosureStatus.OVERDUE),
        awaiting_decision=statuses.count(ClosureStatus.AWAITING_DECISION),
        in_grace_period=statuses.count(ClosureStatus.IN_GRACE_PERIOD),
    )
