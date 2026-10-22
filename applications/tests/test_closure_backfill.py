"""The 0002 migration's backfill: linking old closure-cause rows to the closure they belong to.

``match_closures`` is pure, so most cases here need no database. Every case
where the link would be a guess must leave the row unlinked: a restore then
never puts anyone back on a guess.
"""

import importlib
from datetime import UTC, datetime

import pytest
from django.apps import apps

from applications.models import StageChange
from applications.stages import Stage
from notifications.models import CandidateMessage
from openings.models import OpeningEvent

backfill = importlib.import_module("applications.migrations.0002_stage_change_closure")
match_closures = backfill.match_closures


def at(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 10, day, hour, tzinfo=UTC)


FIRST, SECOND = (10, at(1)), (20, at(5))  # two "closed" events, pk and time


def test_no_closure_links_nothing():
    assert match_closures([(1, at(2))], [], set()) == {}


def test_one_closure_links_every_row_without_looking_at_timestamps():
    rows = [(1, at(9)), (2, at(1, 0))]  # even times that make no sense
    assert match_closures(rows, [FIRST], set()) == {1: 10, 2: 10}


def test_one_email_per_row_pairs_rows_with_closures_in_order_ignoring_timestamps():
    # Both rows carry the same timestamp, which alone couldn't tell them apart.
    rows = [(1, at(5)), (2, at(5))]
    assert match_closures(rows, [FIRST, SECOND], {10, 20}) == {1: 10, 2: 20}


def test_emails_for_another_openings_closures_are_ignored():
    rows = [(1, at(2)), (2, at(6))]
    assert match_closures(rows, [FIRST, SECOND], {10, 20, 99}) == {1: 10, 2: 20}


def test_without_emails_a_row_strictly_inside_one_window_is_linked():
    rows = [(1, at(2)), (2, at(6))]
    assert match_closures(rows, [FIRST, SECOND], set()) == {1: 10, 2: 20}


def test_a_row_tied_with_a_closures_time_stays_unlinked():
    rows = [(1, at(5)), (2, at(6))]  # row 1 at the very moment of the second closure
    assert match_closures(rows, [FIRST, SECOND], set()) == {2: 20}


def test_a_row_before_every_closure_stays_unlinked():
    assert match_closures([(1, at(1, 0))], [FIRST, SECOND], set()) == {}


def test_a_window_that_disagrees_with_the_emails_stays_unlinked():
    # Three rows but only one email, for the first closure: a window pointing at the
    # second closure contradicts the emails, so that row stays unlinked.
    rows = [(1, at(2)), (2, at(3)), (3, at(6))]
    assert match_closures(rows, [FIRST, SECOND], {10}) == {1: 10, 2: 10}


def test_a_repeat_cancellation_in_the_same_closure_follows_its_window():
    # Cancelled at the first closure, put back by hand, cancelled again before it reopened
    # (one email for that closure), then cancelled at the second.
    rows = [(1, at(2)), (2, at(3)), (3, at(6))]
    assert match_closures(rows, [FIRST, SECOND], {10, 20}) == {1: 10, 2: 10, 3: 20}


def test_rows_out_of_order_with_their_windows_stay_unlinked():
    rows = [(1, at(6)), (2, at(2))]  # a later row whose time points at an earlier closure
    assert match_closures(rows, [FIRST, SECOND], set()) == {1: 20}


@pytest.mark.django_db
def test_the_backfill_links_existing_rows_through_the_email_log(app, backend, recruiter):
    ann = app  # Ann's application, at Applied
    first = OpeningEvent.objects.create(
        opening=backend, kind=OpeningEvent.Kind.CLOSED, by=recruiter
    )
    second = OpeningEvent.objects.create(
        opening=backend, kind=OpeningEvent.Kind.CLOSED, by=recruiter
    )
    rows = []
    for closure, from_stage, to_stage in (
        (first, Stage.APPLIED, Stage.REJECTED),
        (None, Stage.REJECTED, Stage.APPLIED),
        (second, Stage.APPLIED, Stage.REJECTED),
    ):
        cause = StageChange.Cause.MANUAL if closure is None else StageChange.Cause.CLOSURE
        rows.append(
            StageChange.objects.create(
                application=ann,
                from_stage=from_stage,
                to_stage=to_stage,
                changed_by=recruiter,
                cause=cause,
            )
        )
        if closure is not None:
            CandidateMessage.objects.create(
                candidate=ann.candidate,
                application=ann,
                kind=CandidateMessage.Kind.CANCELLED,
                occasion=f"closure-{closure.pk}",
                subject="s",
                body="b",
            )
    # Every row written in the same instant: timestamps alone couldn't link them.
    StageChange.objects.filter(application=ann).update(changed_at=second.at)

    backfill.link_cancellations(apps, None)

    linked = [row.closure_id for row in StageChange.objects.filter(pk__in=[r.pk for r in rows])]
    assert linked == [first.pk, None, second.pk]
