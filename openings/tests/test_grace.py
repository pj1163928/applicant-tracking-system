"""The pure grace-period schedule: which reminder is due on a day, and when a grace period ends.

This file has no ``django_db`` mark on purpose: pytest-django fails any test
here that touches the database. Every function takes dates only, and "today"
is always passed in.
"""

from datetime import date

import pytest

from openings.grace import ClosureStatus, closure_status, due_reminder, grace_period_has_ended
from openings.models import GraceExpiryAction

ENDS = date(2026, 11, 10)
AWAITING = ClosureStatus.AWAITING_DECISION
IN_GRACE = ClosureStatus.IN_GRACE_PERIOD
OVERDUE = ClosureStatus.OVERDUE
FLAG = GraceExpiryAction.FLAG_OVERDUE
AUTO = GraceExpiryAction.AUTO_CANCEL

# Written out by hand: (when it was set or last extended, today, the reminder due).
# The 3-day reminder falls on Nov 7 and the 1-day one on Nov 9. A reminder dated on
# or before the day it was set is skipped. A late run sends only the latest reminder
# that's due, and none is due from the end date on.
DUE_REMINDERS = [
    # 7 days, set Nov 3: both reminders.
    (date(2026, 11, 3), date(2026, 11, 3), None),  # the day it was set
    (date(2026, 11, 3), date(2026, 11, 6), None),  # 4 days left
    (date(2026, 11, 3), date(2026, 11, 7), 3),  # 3 days left
    (date(2026, 11, 3), date(2026, 11, 8), 3),  # still the 3-day one; the 1-day isn't due yet
    (date(2026, 11, 3), date(2026, 11, 9), 1),  # 1 day left, even if the 3-day one was missed
    (date(2026, 11, 3), date(2026, 11, 10), None),  # the end date: expiry, not a reminder
    (date(2026, 11, 3), date(2026, 11, 11), None),  # after the end
    # 4 days, set Nov 6: both reminders.
    (date(2026, 11, 6), date(2026, 11, 7), 3),
    (date(2026, 11, 6), date(2026, 11, 9), 1),
    # 3 days, set Nov 7: the 3-day reminder would be on the day it was set, so skipped.
    (date(2026, 11, 7), date(2026, 11, 7), None),
    (date(2026, 11, 7), date(2026, 11, 8), None),
    (date(2026, 11, 7), date(2026, 11, 9), 1),
    # 2 days, set Nov 8: only the 1-day reminder.
    (date(2026, 11, 8), date(2026, 11, 8), None),
    (date(2026, 11, 8), date(2026, 11, 9), 1),
    # 1 day, set Nov 9: both reminder dates are on or before the day it was set.
    (date(2026, 11, 9), date(2026, 11, 9), None),
    (date(2026, 11, 9), date(2026, 11, 10), None),
]


@pytest.mark.parametrize(("set_on", "today", "expected"), DUE_REMINDERS)
def test_due_reminder_matches_the_hand_written_schedule(set_on, today, expected):
    assert due_reminder(ends=ENDS, set_on=set_on, today=today) == expected


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2026, 11, 9), False),  # the day before the end
        (date(2026, 11, 10), True),  # the end date itself
        (date(2026, 11, 11), True),  # the day after
    ],
)
def test_a_grace_period_ends_on_its_end_date_not_the_day_after(today, expected):
    assert grace_period_has_ended(ends=ENDS, today=today) is expected


# Written out by hand: (end date, expiry action, the day process_grace_periods ended it,
# today, the status). Nov 10 is the end date. "In grace period" lasts only while today is
# before it; from the end date itself, not the day after, a flag-overdue grace period is
# overdue whether or not the daily run has handled it, and so is an auto-cancel one the
# run hasn't cancelled yet. Once the run has auto-cancelled, anyone put back in progress
# leaves the opening awaiting a decision.
CLOSURE_STATUSES = [
    # No grace period: awaiting a decision, whatever the day.
    (None, "", None, date(2026, 11, 9), AWAITING),
    (None, "", None, date(2026, 11, 10), AWAITING),
    (None, "", None, date(2026, 11, 11), AWAITING),
    # Flag overdue, not yet handled by the daily run.
    (ENDS, FLAG, None, date(2026, 11, 3), IN_GRACE),  # a week to go
    (ENDS, FLAG, None, date(2026, 11, 9), IN_GRACE),  # the day before the end
    (ENDS, FLAG, None, date(2026, 11, 10), OVERDUE),  # the end date itself
    (ENDS, FLAG, None, date(2026, 11, 11), OVERDUE),  # the day after
    # Flag overdue, handled by the daily run on the end date.
    (ENDS, FLAG, ENDS, date(2026, 11, 10), OVERDUE),
    (ENDS, FLAG, ENDS, date(2026, 11, 20), OVERDUE),
    # Auto-cancel, not yet handled: overdue from the end date, since the cancel is late.
    (ENDS, AUTO, None, date(2026, 11, 3), IN_GRACE),
    (ENDS, AUTO, None, date(2026, 11, 9), IN_GRACE),
    (ENDS, AUTO, None, date(2026, 11, 10), OVERDUE),
    (ENDS, AUTO, None, date(2026, 11, 11), OVERDUE),
    # Auto-cancel, already handled: only "cancel now" is left for anyone back in progress.
    (ENDS, AUTO, ENDS, date(2026, 11, 10), AWAITING),
    (ENDS, AUTO, ENDS, date(2026, 11, 11), AWAITING),
    (ENDS, AUTO, ENDS, date(2026, 11, 20), AWAITING),
    # Years in the past: the status follows the "today" passed in, never the clock.
    (date(2020, 1, 10), FLAG, None, date(2020, 1, 9), IN_GRACE),
    (date(2020, 1, 10), FLAG, None, date(2020, 1, 10), OVERDUE),
]


@pytest.mark.parametrize(("ends", "action", "expired_on", "today", "expected"), CLOSURE_STATUSES)
def test_closure_status_matches_the_hand_written_table(ends, action, expired_on, today, expected):
    assert closure_status(ends=ends, action=action, expired_on=expired_on, today=today) == expected
