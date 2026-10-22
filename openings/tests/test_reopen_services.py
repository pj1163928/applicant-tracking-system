"""Reopening an opening: reopen_opening() and its refusals."""

from datetime import date

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from applications.models import StageChange
from applications.stages import Stage
from notifications.models import CandidateMessage
from openings.models import JobOpening, OpeningEvent
from openings.services import ALREADY_OPEN, process_grace_periods, reopen_opening
from openings.tests.conftest import close_directly, grace_directly

pytestmark = pytest.mark.django_db

SET_ON = date(2026, 11, 2)
ENDS = date(2026, 11, 9)  # the 3-day reminder falls on Nov 6


def snapshot(opening):
    stored = JobOpening.objects.get(pk=opening.pk)
    return (
        stored.status,
        stored.grace_period_ends,
        OpeningEvent.objects.count(),
        StageChange.objects.count(),
        CandidateMessage.objects.count(),
    )


@pytest.mark.parametrize("role", ["admin", "recruiter", "hiring_manager"])
def test_anyone_who_may_close_an_opening_may_reopen_it(request, backend, recruiter, role):
    user = request.getfixturevalue(role)
    close_directly(backend, recruiter)

    event = reopen_opening(backend, by=user, note="  Budget approved after all.  ")

    assert JobOpening.objects.get(pk=backend.pk).status == JobOpening.Status.OPEN
    assert backend.is_open
    assert (event.kind, event.by, event.note) == (
        OpeningEvent.Kind.REOPENED,
        user,
        "Budget approved after all.",
    )
    assert backend.events.first() == event


@pytest.mark.parametrize("role", ["interviewer", "no_role_user", "inactive_manager"])
def test_reopening_is_refused_for_other_users_and_writes_nothing(request, backend, recruiter, role):
    close_directly(backend, recruiter)
    before = snapshot(backend)

    with pytest.raises(PermissionDenied, match="can reopen openings"):
        reopen_opening(backend, by=request.getfixturevalue(role))

    assert snapshot(backend) == before


def test_reopening_an_open_opening_is_refused(backend, recruiter):
    before = snapshot(backend)

    with pytest.raises(ValidationError) as refused:
        reopen_opening(backend, by=recruiter)

    assert refused.value.code == ALREADY_OPEN
    assert snapshot(backend) == before


def test_reopening_judges_the_stored_status_not_the_callers_copy(backend, recruiter):
    stale = JobOpening.objects.get(pk=backend.pk)
    close_directly(backend, recruiter)
    reopen_opening(backend, by=recruiter)
    stale.status = JobOpening.Status.CLOSED  # the copy still thinks it is closed

    with pytest.raises(ValidationError):
        reopen_opening(stale, by=recruiter)
    assert backend.events.filter(kind=OpeningEvent.Kind.REOPENED).count() == 1


def test_reopening_clears_the_grace_period_and_says_so(backend, recruiter, hiring_manager):
    close_directly(backend, recruiter)
    grace_directly(
        backend,
        by=hiring_manager,
        ends=ENDS,
        set_on=SET_ON,
        action=JobOpening.GraceExpiryAction.AUTO_CANCEL,
    )

    event = reopen_opening(backend, by=recruiter)

    stored = JobOpening.objects.get(pk=backend.pk)
    fields = (
        stored.grace_period_ends,
        stored.grace_expiry_action,
        stored.grace_period_set_on,
        stored.grace_expired_on,
    )
    assert fields == (None, "", None, None)
    assert (backend.grace_period_ends, backend.has_grace_period) == (None, False)
    assert event.note == "Cleared the grace period ending Nov 9, 2026."


def test_reopening_clears_an_ended_grace_period_too(backend, recruiter, hiring_manager):
    close_directly(backend, recruiter)
    grace_directly(
        backend,
        by=hiring_manager,
        ends=ENDS,
        set_on=SET_ON,
        action=JobOpening.GraceExpiryAction.FLAG_OVERDUE,
    )
    JobOpening.objects.filter(pk=backend.pk).update(grace_expired_on=ENDS)

    event = reopen_opening(backend, by=recruiter, note="Hiring again.")

    stored = JobOpening.objects.get(pk=backend.pk)
    assert (stored.grace_period_ends, stored.grace_expired_on) == (None, None)
    assert event.note == "Hiring again."  # an ended grace period isn't mentioned


def test_reopening_stops_reminders_and_the_grace_periods_end(
    backend,
    recruiter,
    hiring_manager,
    make_candidate,
    application_at,
    mailoutbox,
    django_capture_on_commit_callbacks,
):
    ann = application_at(make_candidate("Ann"), backend, Stage.SCREENING)
    close_directly(backend, recruiter)
    grace_directly(
        backend,
        by=hiring_manager,
        ends=ENDS,
        set_on=SET_ON,
        action=JobOpening.GraceExpiryAction.AUTO_CANCEL,
    )
    reopen_opening(backend, by=recruiter)

    with django_capture_on_commit_callbacks(execute=True):
        reminder_day = process_grace_periods(today=date(2026, 11, 6))
        end_day = process_grace_periods(today=ENDS)

    assert (reminder_day.reminders_sent, end_day.expired) == (0, [])
    assert mailoutbox == []
    assert ann.stage_changes.last().to_stage == Stage.SCREENING  # never auto-cancelled


def test_reopening_leaves_applications_where_they_are(
    backend, recruiter, make_candidate, application_at
):
    ann = application_at(make_candidate("Ann"), backend, Stage.INTERVIEW)
    close_directly(backend, recruiter)
    history = StageChange.objects.count()

    reopen_opening(backend, by=recruiter)

    assert StageChange.objects.count() == history
    assert backend.applications.get(pk=ann.pk).stage == Stage.INTERVIEW
