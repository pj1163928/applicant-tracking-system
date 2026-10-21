import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, connection

from applications.models import Application, StageChange
from applications.services import CLOSED_OPENING, move_application, record_application
from applications.stages import Stage
from applications.tests.test_moves import FailOn
from notifications.models import CandidateMessage
from openings.models import JobOpening, OpeningEvent
from openings.services import (
    ALREADY_CLOSED,
    CLOSURE_NOTE,
    NOT_CLOSED,
    cancel_remaining_applications,
    close_opening,
)
from openings.tests.conftest import close_directly

pytestmark = pytest.mark.django_db


def test_cancel_now_rejects_only_the_active_applications_with_cause_closure_and_the_note(
    backend, hiring_manager, make_candidate, application_at
):
    applications = {
        stage: application_at(make_candidate(stage.label.replace(" ", "")), backend, stage)
        for stage in Stage
    }
    close_directly(backend, hiring_manager)
    ended = {Stage.HIRED, Stage.REJECTED, Stage.WITHDRAWN}
    history_before = {
        stage: list(application.stage_changes.values_list("pk", flat=True))
        for stage, application in applications.items()
    }

    rows = cancel_remaining_applications(backend, by=hiring_manager)

    stages_now = {
        stage: Application.objects.get(pk=application.pk).stage
        for stage, application in applications.items()
    }
    assert stages_now == {stage: Stage.REJECTED if stage not in ended else stage for stage in Stage}
    assert sorted(
        (row.from_stage, row.to_stage, row.cause, row.note, row.changed_by_id) for row in rows
    ) == sorted(
        (stage, Stage.REJECTED, StageChange.Cause.CLOSURE, CLOSURE_NOTE, hiring_manager.pk)
        for stage in Stage
        if stage not in ended
    )
    for stage in ended:  # finished applications get no new history
        history = list(applications[stage].stage_changes.values_list("pk", flat=True))
        assert history == history_before[stage]


@pytest.fixture
def ann(make_candidate):
    return make_candidate("Ann")


@pytest.fixture
def ben(make_candidate):
    return make_candidate("Ben")


def snapshot(opening):
    """Everything closing and cancelling may write, to prove a refusal wrote nothing."""
    return (
        JobOpening.objects.get(pk=opening.pk).status,
        sorted(opening.applications.values_list("pk", "stage")),
        StageChange.objects.count(),
        OpeningEvent.objects.count(),
        CandidateMessage.objects.count(),
    )


# Closing


def test_closing_writes_a_closed_event_and_stops_new_applications(
    backend, recruiter, ann, indeed, django_capture_on_commit_callbacks, mailoutbox
):
    with django_capture_on_commit_callbacks(execute=True):
        event = close_opening(backend, by=recruiter, note="  Budget moved to next year.  ")

    backend.refresh_from_db()
    assert backend.status == JobOpening.Status.CLOSED
    assert list(backend.events.values_list("kind", "by", "note")) == [
        (OpeningEvent.Kind.CLOSED, recruiter.pk, "Budget moved to next year.")
    ]
    assert event.pk == backend.events.get().pk
    assert mailoutbox == []  # nobody was in progress, so the authority has nothing to decide
    with pytest.raises(ValidationError) as refused:
        record_application(candidate=ann, opening=backend, source=indeed, by=recruiter)
    assert refused.value.code == CLOSED_OPENING


def test_closing_with_active_applications_emails_the_authority_once(
    backend,
    recruiter,
    hiring_manager,
    ann,
    ben,
    application_at,
    django_capture_on_commit_callbacks,
    mailoutbox,
):
    hiring_manager.email = "hal@example.com"
    hiring_manager.save()
    application_at(ann, backend, Stage.INTERVIEW)
    application_at(ben, backend, Stage.HIRED)  # finished, so not counted

    with django_capture_on_commit_callbacks(execute=True):
        close_opening(backend, by=recruiter, note="Paused.")

    assert len(mailoutbox) == 1
    email = mailoutbox[0]
    assert email.to == ["hal@example.com"]
    assert email.subject == "Backend Developer closed with 1 applicant still in progress"
    body = " ".join(email.body.split())
    assert 'Rae Recruiter closed Backend Developer (Engineering). Their note: "Paused."' in body
    assert "you decide what happens to them" in body


@pytest.mark.parametrize("user_fixture", ["interviewer", "no_role_user"])
def test_only_admins_recruiters_and_hiring_managers_can_close(request, backend, user_fixture):
    before = snapshot(backend)

    with pytest.raises(PermissionDenied):
        close_opening(backend, by=request.getfixturevalue(user_fixture))

    assert snapshot(backend) == before


def test_closing_a_closed_opening_is_refused_and_writes_nothing(
    backend,
    recruiter,
    hiring_manager,
    ann,
    application_at,
    django_capture_on_commit_callbacks,
    mailoutbox,
):
    hiring_manager.email = "hal@example.com"
    hiring_manager.save()
    application_at(ann, backend, Stage.APPLIED)
    stale = JobOpening.objects.get(pk=backend.pk)  # a copy loaded while it was still open
    with django_capture_on_commit_callbacks(execute=True):
        close_opening(backend, by=recruiter)
    before = snapshot(backend)

    with (
        django_capture_on_commit_callbacks(execute=True),
        pytest.raises(ValidationError) as refused,
    ):
        close_opening(stale, by=recruiter)

    assert refused.value.code == ALREADY_CLOSED
    assert snapshot(backend) == before
    assert len(mailoutbox) == 1  # only the first close emailed the authority


@pytest.mark.parametrize(
    ("start", "path"),
    [
        (Stage.APPLIED, [Stage.SCREENING]),
        (Stage.FINAL_REVIEW, [Stage.OFFER, Stage.HIRED]),
    ],
)
def test_applications_keep_moving_after_closing_including_into_offer_and_hired(
    backend, recruiter, hiring_manager, ann, application_at, start, path
):
    application = application_at(ann, backend, start)
    close_opening(backend, by=recruiter)

    for stage in path:
        move_application(application, stage, by=hiring_manager)

    assert Application.objects.get(pk=application.pk).stage == path[-1]


# Cancel now


@pytest.mark.parametrize("user_fixture", ["recruiter", "interviewer", "no_role_user"])
def test_only_closure_deciders_can_cancel_and_a_refusal_changes_nothing(
    request, backend, hiring_manager, ann, application_at, user_fixture
):
    application_at(ann, backend, Stage.INTERVIEW)
    close_directly(backend, hiring_manager)
    before = snapshot(backend)

    with pytest.raises(PermissionDenied) as refused:
        cancel_remaining_applications(backend, by=request.getfixturevalue(user_fixture))

    assert "Hal Manager, this opening's designated authority" in str(refused.value)
    assert snapshot(backend) == before


def test_a_recruiter_who_is_the_authority_can_cancel(
    skilled_opening, authority, ann, application_at
):
    application = application_at(ann, skilled_opening, Stage.SCREENING)
    close_directly(skilled_opening, authority)

    cancel_remaining_applications(skilled_opening, by=authority)

    assert Application.objects.get(pk=application.pk).stage == Stage.REJECTED


def test_cancelling_an_open_opening_is_refused_and_changes_nothing(
    backend, hiring_manager, ann, application_at
):
    application_at(ann, backend, Stage.INTERVIEW)
    before = snapshot(backend)

    with pytest.raises(ValidationError) as refused:
        cancel_remaining_applications(backend, by=hiring_manager)

    assert refused.value.code == NOT_CLOSED
    assert snapshot(backend) == before


def test_cancel_now_emails_each_cancelled_candidate_once_and_writes_one_event(
    backend,
    hiring_manager,
    ann,
    ben,
    make_candidate,
    application_at,
    django_capture_on_commit_callbacks,
    mailoutbox,
):
    application_at(ann, backend, Stage.APPLIED)
    application_at(ben, backend, Stage.OFFER)
    application_at(make_candidate("Cy"), backend, Stage.WITHDRAWN)  # not cancelled, not emailed
    close_directly(backend, hiring_manager)

    with django_capture_on_commit_callbacks(execute=True):
        rows = cancel_remaining_applications(backend, by=hiring_manager)

    assert len(rows) == 2
    assert sorted(m.to[0] for m in mailoutbox) == ["ann@example.com", "ben@example.com"]
    assert {m.subject for m in mailoutbox} == {"Your application for Backend Developer"}
    assert all(
        "our team will be in touch to complete the next step" in " ".join(m.body.split())
        for m in mailoutbox
    )
    assert sorted(CandidateMessage.objects.values_list("candidate__first_name", "kind")) == [
        ("Ann", CandidateMessage.Kind.CANCELLED),
        ("Ben", CandidateMessage.Kind.CANCELLED),
    ]
    assert list(backend.events.values_list("kind", "by")) == [
        (OpeningEvent.Kind.APPLICATIONS_CANCELLED, hiring_manager.pk),
        (OpeningEvent.Kind.CLOSED, hiring_manager.pk),
    ]


def test_cancelling_again_changes_nothing_writes_no_event_and_sends_no_email(
    backend, hiring_manager, ann, application_at, django_capture_on_commit_callbacks, mailoutbox
):
    application_at(ann, backend, Stage.INTERVIEW)
    close_directly(backend, hiring_manager)
    with django_capture_on_commit_callbacks(execute=True):
        cancel_remaining_applications(backend, by=hiring_manager)
    before = snapshot(backend)

    with django_capture_on_commit_callbacks(execute=True):
        rows = cancel_remaining_applications(backend, by=hiring_manager)

    assert rows == []
    assert snapshot(backend) == before
    assert len(mailoutbox) == 1


def test_a_second_cancel_in_the_same_closure_adds_no_event_or_repeat_email(
    backend,
    hiring_manager,
    ann,
    ben,
    application_at,
    django_capture_on_commit_callbacks,
    mailoutbox,
):
    ann_application = application_at(ann, backend, Stage.INTERVIEW)
    ben_application = application_at(ben, backend, Stage.WITHDRAWN)  # not cancelled the first time
    close_directly(backend, hiring_manager)
    with django_capture_on_commit_callbacks(execute=True):
        cancel_remaining_applications(backend, by=hiring_manager)
    # Both are reopened by hand while the opening is still closed.
    move_application(ann_application, Stage.SCREENING, by=hiring_manager, note="Changed our mind.")
    move_application(ben_application, Stage.APPLIED, by=hiring_manager, note="Back after all.")

    with django_capture_on_commit_callbacks(execute=True):
        rows = cancel_remaining_applications(backend, by=hiring_manager)

    assert {row.application.candidate.first_name for row in rows} == {"Ann", "Ben"}
    assert backend.events.filter(kind=OpeningEvent.Kind.APPLICATIONS_CANCELLED).count() == 1
    # Ann already had this closure's email; only Ben gets one now.
    assert [m.to[0] for m in mailoutbox] == ["ann@example.com", "ben@example.com"]


def test_a_later_closure_gets_its_own_event_and_emails(
    backend, hiring_manager, ann, application_at, django_capture_on_commit_callbacks, mailoutbox
):
    application = application_at(ann, backend, Stage.INTERVIEW)
    close_directly(backend, hiring_manager)
    with django_capture_on_commit_callbacks(execute=True):
        cancel_remaining_applications(backend, by=hiring_manager)
    # Back in progress, then the opening is closed a second time.
    move_application(application, Stage.INTERVIEW, by=hiring_manager, note="Back in.")
    close_directly(backend, hiring_manager)

    with django_capture_on_commit_callbacks(execute=True):
        cancel_remaining_applications(backend, by=hiring_manager)

    assert backend.events.filter(kind=OpeningEvent.Kind.APPLICATIONS_CANCELLED).count() == 2
    assert CandidateMessage.objects.count() == 2
    assert len(mailoutbox) == 2


@pytest.mark.parametrize(
    "failing_write",
    [
        'INSERT INTO "applications_stagechange"',
        'UPDATE "applications_application"',
        'INSERT INTO "notifications_candidatemessage"',
        'INSERT INTO "openings_openingevent"',
    ],
)
def test_if_any_write_fails_the_whole_cancel_is_undone_and_a_retry_works(
    backend,
    hiring_manager,
    ann,
    ben,
    application_at,
    django_capture_on_commit_callbacks,
    mailoutbox,
    failing_write,
):
    application_at(ann, backend, Stage.APPLIED)
    application_at(ben, backend, Stage.OFFER)
    close_directly(backend, hiring_manager)
    before = snapshot(backend)

    with (
        django_capture_on_commit_callbacks(execute=True),
        connection.execute_wrapper(FailOn(failing_write)),
        pytest.raises(DatabaseError),
    ):
        cancel_remaining_applications(backend, by=hiring_manager)

    assert snapshot(backend) == before
    assert mailoutbox == []

    with django_capture_on_commit_callbacks(execute=True):
        rows = cancel_remaining_applications(backend, by=hiring_manager)

    assert len(rows) == 2
    assert len(mailoutbox) == 2
    assert backend.events.filter(kind=OpeningEvent.Kind.APPLICATIONS_CANCELLED).count() == 1
