"""The grace-period schedule: which reminder is due on a given day, and when a grace period ends.

A pure module: every function here takes dates only. None of them reads the
database, the clock or a user, so "today" is always passed in and tests can
choose it. Dates are calendar days in the project time zone.
"""

from datetime import date, timedelta

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
