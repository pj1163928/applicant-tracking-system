"""The grace-period schedule: which reminder is due on a given day, when a grace period ends,
and where a closed opening stands.

A pure module: every function here takes dates (and an expiry action) only.
None of them reads the database, the clock or a user, so "today" is always
passed in and tests can choose it. Dates are calendar days in the project time zone.
"""

from datetime import date, timedelta

from django.db import models

from openings.models import GraceExpiryAction

# Days left when each reminder goes out, fewest first: a late run sends the first one due.
REMINDER_DAYS: tuple[int, ...] = (1, 3)


def due_reminder(*, ends: date, set_on: date, today: date) -> int | None:
    """Return the reminder due on ``today`` (3 or 1 days left), or None if none is due.

    The 3-day reminder falls on ``ends`` - 3 and the 1-day one on ``ends`` - 1.
    A reminder dated on or before ``set_on`` (the day the grace period was set
    or last extended) is skipped, so a 3-day grace period gets only the 1-day
    reminder and a 1-day one gets none. A late run returns only the most recent
    reminder that's due, never one for a stale date, and none is due once
    ``today`` reaches ``ends``. The same reminder stays due on later days until
    the next one is; the message's identity is what stops it being sent twice.
    """
    if grace_period_has_ended(ends=ends, today=today):
        return None
    for days_left in REMINDER_DAYS:
        on = ends - timedelta(days=days_left)
        if set_on < on <= today:
            return days_left
    return None


def grace_period_has_ended(*, ends: date, today: date) -> bool:
    """Return True from the end date on: expiry happens on ``ends`` itself, not the day after."""
    return today >= ends


class ClosureStatus(models.TextChoices):
    """Where a closed opening with applicants still in progress stands, for the in-progress view."""

    AWAITING_DECISION = "awaiting_decision", "Awaiting decision"
    IN_GRACE_PERIOD = "in_grace_period", "In grace period"
    OVERDUE = "overdue", "Overdue"


def closure_status(
    *, ends: date | None, action: str, expired_on: date | None, today: date
) -> ClosureStatus:
    """Return where a closed opening with applicants still in progress stands on ``today``.

    ``ends`` and ``action`` are its grace period's end date and expiry action
    (None and "" without one), and ``expired_on`` is the day
    ``process_grace_periods`` ended it, if it has.

    - Awaiting decision: no grace period, or an auto-cancel one the daily run
      has already ended (anyone back in progress since is left to decide).
    - In grace period: a grace period is set and ``today`` is before ``ends``.
    - Overdue: from ``ends`` itself, not the day after, when the action is flag
      overdue, or auto-cancel and the daily run hasn't cancelled yet. So a
      late or missed run still shows.
    """
    if ends is None:
        return ClosureStatus.AWAITING_DECISION
    if not grace_period_has_ended(ends=ends, today=today):
        return ClosureStatus.IN_GRACE_PERIOD
    if action == GraceExpiryAction.AUTO_CANCEL and expired_on is not None:
        return ClosureStatus.AWAITING_DECISION
    return ClosureStatus.OVERDUE
