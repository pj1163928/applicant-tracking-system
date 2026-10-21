from datetime import date

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, connection

from accounts.roles import HIRING_MANAGER
from applications.models import Application, StageChange
from applications.services import move_application
from applications.stages import Stage
from applications.tests.test_moves import FailOn
from notifications.models import CandidateMessage
from openings.models import JobOpening, OpeningEvent
from openings.services import (
    CLOSURE_NOTE,
    GRACE_ALREADY_CANCELLED,
    GRACE_PERIOD_EXISTS,
    INVALID_EXPIRY_ACTION,
    INVALID_GRACE_DAYS,
    INVALID_GRACE_END,
    NO_GRACE_PERIOD,
    NOT_CLOSED,
    NOTE_REQUIRED,
    NOTHING_IN_PROGRESS,
    cancel_remaining_applications,
    extend_grace_period,
    process_grace_periods,
    set_grace_period,
)
from openings.tests.conftest import close_directly, grace_directly

pytestmark = pytest.mark.django_db

FLAG_OVERDUE = JobOpening.GraceExpiryAction.FLAG_OVERDUE
AUTO_CANCEL = JobOpening.GraceExpiryAction.AUTO_CANCEL

# Every grace period in these tests was set on Nov 3 and ends on Nov 10, 2026.
SET_ON = date(2026, 11, 3)
ENDS = date(2026, 11, 10)


@pytest.fixture
def ann(make_candidate):
    return make_candidate("Ann")


@pytest.fixture
def ben(make_candidate):
    return make_candidate("Ben")


def grace_snapshot(opening):
    """Everything a grace-period run may write, to prove a second run wrote nothing."""
    stored = JobOpening.objects.get(pk=opening.pk)
    return (
        stored.grace_period_ends,
        stored.grace_expiry_action,
        stored.grace_period_set_on,
        stored.grace_expired_on,
        sorted(opening.applications.values_list("pk", "stage")),
        StageChange.objects.count(),
        list(OpeningEvent.objects.values_list("pk", "kind", "note")),
        sorted(CandidateMessage.objects.values_list("pk", "kind", "occasion")),
    )


def test_running_twice_on_the_same_day_sends_each_reminder_once_and_changes_nothing_more(
    backend,
    hiring_manager,
    ann,
    ben,
    make_candidate,
    application_at,
    django_capture_on_commit_callbacks,
    mailoutbox,
):
    application_at(ann, backend, Stage.INTERVIEW)
    application_at(ben, backend, Stage.APPLIED)
    application_at(make_candidate("Cy"), backend, Stage.HIRED)  # finished: no reminder
    close_directly(backend, hiring_manager)
    grace_directly(backend, by=hiring_manager, ends=ENDS, set_on=SET_ON, action=FLAG_OVERDUE)

    with django_capture_on_commit_callbacks(execute=True):
        first = process_grace_periods(today=date(2026, 11, 7))  # the 3-day reminder's day

    assert first.reminders_sent == 2
    assert sorted(m.to[0] for m in mailoutbox) == ["ann@example.com", "ben@example.com"]
    assert {m.subject for m in mailoutbox} == {
        "3 days left on your application for Backend Developer"
    }
    before = grace_snapshot(backend)

    with django_capture_on_commit_callbacks(execute=True):
        second = process_grace_periods(today=date(2026, 11, 7))

    assert second.reminders_sent == 0
    assert grace_snapshot(backend) == before
    assert len(mailoutbox) == 2


# The end of a grace period. Hand-written outcomes: the stage of each applicant, the
# day the end was handled, the opening's events (newest first) and the emails sent.
NOT_ENDED = {
    "stages": {"Ann": Stage.INTERVIEW, "Ben": Stage.APPLIED, "Cy": Stage.HIRED},
    "expired_on": None,
    "events": [
        (OpeningEvent.Kind.GRACE_PERIOD_SET, "manager"),
        (OpeningEvent.Kind.CLOSED, "manager"),
    ],
    # The day before the end is only the 1-day reminder's day.
    "emails": [
        ("ann@example.com", "1 day left on your application for Backend Developer"),
        ("ben@example.com", "1 day left on your application for Backend Developer"),
    ],
}
AUTO_CANCELLED = {
    "stages": {"Ann": Stage.REJECTED, "Ben": Stage.REJECTED, "Cy": Stage.HIRED},
    "events": [
        (OpeningEvent.Kind.APPLICATIONS_CANCELLED, "manager"),
        (OpeningEvent.Kind.GRACE_PERIOD_EXPIRED, "manager"),
        (OpeningEvent.Kind.GRACE_PERIOD_SET, "manager"),
        (OpeningEvent.Kind.CLOSED, "manager"),
    ],
    "emails": [
        ("ann@example.com", "Your application for Backend Developer"),
        ("ben@example.com", "Your application for Backend Developer"),
    ],
}
FLAGGED_OVERDUE = {
    "stages": {"Ann": Stage.INTERVIEW, "Ben": Stage.APPLIED, "Cy": Stage.HIRED},
    "events": [
        (OpeningEvent.Kind.GRACE_PERIOD_EXPIRED, "manager"),
        (OpeningEvent.Kind.GRACE_PERIOD_SET, "manager"),
        (OpeningEvent.Kind.CLOSED, "manager"),
    ],
    "emails": [("hal@example.com", "Backend Developer is overdue: 2 applicants still in progress")],
}


@pytest.fixture
def ending(
    backend, hiring_manager, ann, ben, make_candidate, application_at
) -> dict[str, Application]:
    """Backend Developer, with Ann and Ben in progress and Cy hired. Tests close it themselves."""
    hiring_manager.email = "hal@example.com"
    hiring_manager.save()
    applications = {
        "Ann": application_at(ann, backend, Stage.INTERVIEW),
        "Ben": application_at(ben, backend, Stage.APPLIED),
        "Cy": application_at(make_candidate("Cy"), backend, Stage.HIRED),
    }
    return applications


def outcome(opening, applications, mailoutbox) -> dict:
    """What the end of ``opening``'s grace period has done so far, in the tables' shape."""
    return {
        "stages": {
            name: Application.objects.get(pk=application.pk).stage
            for name, application in applications.items()
        },
        "expired_on": JobOpening.objects.get(pk=opening.pk).grace_expired_on,
        "events": list(opening.events.values_list("kind", "by__username")),
        "emails": sorted((m.to[0], m.subject) for m in mailoutbox),
    }


@pytest.mark.parametrize(
    ("action", "today", "expected"),
    [
        (AUTO_CANCEL, date(2026, 11, 9), NOT_ENDED),  # the day before the end
        (AUTO_CANCEL, date(2026, 11, 10), AUTO_CANCELLED),  # the end date itself
        (AUTO_CANCEL, date(2026, 11, 11), AUTO_CANCELLED),  # the day after (a missed run)
        (FLAG_OVERDUE, date(2026, 11, 9), NOT_ENDED),
        (FLAG_OVERDUE, date(2026, 11, 10), FLAGGED_OVERDUE),
        (FLAG_OVERDUE, date(2026, 11, 11), FLAGGED_OVERDUE),
    ],
)
def test_the_expiry_action_runs_from_the_end_date_on(
    backend,
    hiring_manager,
    ending,
    django_capture_on_commit_callbacks,
    mailoutbox,
    action,
    today,
    expected,
):
    close_directly(backend, hiring_manager)
    grace_directly(backend, by=hiring_manager, ends=ENDS, set_on=SET_ON, action=action)

    with django_capture_on_commit_callbacks(execute=True):
        run = process_grace_periods(today=today)

    ended = expected is not NOT_ENDED
    assert outcome(backend, ending, mailoutbox) == expected | {
        "expired_on": today if ended else None
    }
    assert run.expired == (["Backend Developer"] if ended else [])
    if action == AUTO_CANCEL and ended:  # cancelled the cancel-now way
        assert sorted(
            StageChange.objects.filter(to_stage=Stage.REJECTED).values_list(
                "application__candidate__first_name", "cause", "note"
            )
        ) == [
            ("Ann", StageChange.Cause.CLOSURE, CLOSURE_NOTE),
            ("Ben", StageChange.Cause.CLOSURE, CLOSURE_NOTE),
        ]


@pytest.mark.parametrize("action", [AUTO_CANCEL, FLAG_OVERDUE])
def test_the_expiry_action_runs_only_once_even_after_an_application_is_reopened(
    backend,
    hiring_manager,
    ending,
    make_candidate,
    application_at,
    django_capture_on_commit_callbacks,
    mailoutbox,
    action,
):
    dee = application_at(make_candidate("Dee"), backend, Stage.WITHDRAWN)
    close_directly(backend, hiring_manager)
    grace_directly(backend, by=hiring_manager, ends=ENDS, set_on=SET_ON, action=action)
    with django_capture_on_commit_callbacks(execute=True):
        process_grace_periods(today=ENDS)
    assert JobOpening.objects.get(pk=backend.pk).grace_expired_on == ENDS
    # On the closed opening, someone puts an applicant back in progress by hand.
    move_application(dee, Stage.APPLIED, by=hiring_manager, note="Back after all.")
    if action == AUTO_CANCEL:
        move_application(
            ending["Ann"], Stage.SCREENING, by=hiring_manager, note="Changed our mind."
        )
    before = grace_snapshot(backend)
    sent = len(mailoutbox)

    for later in (ENDS, date(2026, 11, 11), date(2026, 11, 20)):  # same day, next day, later
        with django_capture_on_commit_callbacks(execute=True):
            run = process_grace_periods(today=later)
        assert run.expired == []

    assert grace_snapshot(backend) == before  # no second cancel, flag or "ended" event
    assert len(mailoutbox) == sent  # and no second email to candidates or the authority


# Setting a grace period


def body(message) -> str:
    return " ".join(message.body.split())


@pytest.mark.parametrize(
    ("action", "consequence"),
    [(AUTO_CANCEL, "your application will be closed"), (FLAG_OVERDUE, "may be closed")],
)
def test_setting_stores_the_period_writes_an_event_and_emails_each_active_candidate_once(
    backend,
    hiring_manager,
    ending,
    django_capture_on_commit_callbacks,
    mailoutbox,
    action,
    consequence,
):
    close_directly(backend, hiring_manager)

    with django_capture_on_commit_callbacks(execute=True):
        event = set_grace_period(backend, days=7, action=action, by=hiring_manager, today=SET_ON)

    stored = JobOpening.objects.get(pk=backend.pk)
    assert (
        stored.grace_period_ends,
        stored.grace_expiry_action,
        stored.grace_period_set_on,
        stored.grace_expired_on,
    ) == (ENDS, action, SET_ON, None)
    assert backend.grace_period_ends == ENDS  # the caller's copy is updated too
    then = "cancel the remaining applications" if action == AUTO_CANCEL else "flag the opening"
    assert (event.kind, event.by, event.opening_id) == (
        OpeningEvent.Kind.GRACE_PERIOD_SET,
        hiring_manager,
        backend.pk,
    )
    assert event.note.startswith(f"7 days, ending Nov 10, 2026. When it ends: {then}")
    assert sorted(m.to[0] for m in mailoutbox) == ["ann@example.com", "ben@example.com"]
    assert {m.subject for m in mailoutbox} == {
        "An update on your application for Backend Developer"
    }
    for message in mailoutbox:
        assert "We have until November 10, 2026 to complete the process." in body(message)
        assert consequence in body(message)
        assert "our team will be in touch to complete the next step" in body(message).lower()
    assert sorted(CandidateMessage.objects.values_list("candidate__first_name", "kind")) == [
        ("Ann", CandidateMessage.Kind.GRACE_PERIOD_SET),
        ("Ben", CandidateMessage.Kind.GRACE_PERIOD_SET),
    ]


@pytest.mark.parametrize("user_fixture", ["recruiter", "interviewer", "no_role_user"])
def test_only_closure_deciders_can_set_a_grace_period(
    request, backend, hiring_manager, ending, user_fixture
):
    close_directly(backend, hiring_manager)
    before = grace_snapshot(backend)

    with pytest.raises(PermissionDenied):
        set_grace_period(
            backend, days=7, action=FLAG_OVERDUE, by=request.getfixturevalue(user_fixture)
        )

    assert grace_snapshot(backend) == before


def test_a_recruiter_who_is_the_authority_can_set_one(
    skilled_opening, authority, ann, application_at
):
    application_at(ann, skilled_opening, Stage.SCREENING)
    close_directly(skilled_opening, authority)

    set_grace_period(skilled_opening, days=3, action=AUTO_CANCEL, by=authority, today=SET_ON)

    assert JobOpening.objects.get(pk=skilled_opening.pk).grace_period_ends == date(2026, 11, 6)


@pytest.mark.parametrize(
    ("days", "action", "code"),
    [
        (0, FLAG_OVERDUE, INVALID_GRACE_DAYS),
        (91, FLAG_OVERDUE, INVALID_GRACE_DAYS),
        (7, "", INVALID_EXPIRY_ACTION),
        (7, "delete_everyone", INVALID_EXPIRY_ACTION),
    ],
)
def test_setting_refuses_a_bad_length_or_action_and_writes_nothing(
    backend, hiring_manager, ending, days, action, code
):
    close_directly(backend, hiring_manager)
    before = grace_snapshot(backend)

    with pytest.raises(ValidationError) as refused:
        set_grace_period(backend, days=days, action=action, by=hiring_manager)

    assert refused.value.code == code
    assert grace_snapshot(backend) == before


@pytest.mark.parametrize("days", [1, 90])
def test_setting_accepts_one_to_ninety_days(backend, hiring_manager, ending, days):
    close_directly(backend, hiring_manager)

    set_grace_period(backend, days=days, action=FLAG_OVERDUE, by=hiring_manager, today=SET_ON)

    assert JobOpening.objects.get(pk=backend.pk).grace_period_set_on == SET_ON


def test_setting_on_an_open_opening_is_refused(backend, hiring_manager, ending):
    with pytest.raises(ValidationError) as refused:
        set_grace_period(backend, days=7, action=FLAG_OVERDUE, by=hiring_manager)

    assert refused.value.code == NOT_CLOSED
    assert not JobOpening.objects.get(pk=backend.pk).has_grace_period


def test_setting_with_nobody_in_progress_is_refused(backend, hiring_manager, ann, application_at):
    application_at(ann, backend, Stage.HIRED)
    close_directly(backend, hiring_manager)

    with pytest.raises(ValidationError) as refused:
        set_grace_period(backend, days=7, action=FLAG_OVERDUE, by=hiring_manager)

    assert refused.value.code == NOTHING_IN_PROGRESS


def test_setting_a_second_grace_period_is_refused_and_emails_nobody_again(
    backend, hiring_manager, ending, django_capture_on_commit_callbacks, mailoutbox
):
    close_directly(backend, hiring_manager)
    stale = JobOpening.objects.get(pk=backend.pk)  # loaded before the first one was set
    with django_capture_on_commit_callbacks(execute=True):
        set_grace_period(backend, days=7, action=FLAG_OVERDUE, by=hiring_manager, today=SET_ON)
    before = grace_snapshot(backend)

    with (
        django_capture_on_commit_callbacks(execute=True),
        pytest.raises(ValidationError) as refused,
    ):
        set_grace_period(stale, days=3, action=AUTO_CANCEL, by=hiring_manager)

    assert refused.value.code == GRACE_PERIOD_EXISTS
    assert grace_snapshot(backend) == before
    assert len(mailoutbox) == 2


# Extending


@pytest.fixture
def in_grace(backend, hiring_manager, ending):
    """Backend Developer, closed, in a flag-overdue grace period set Nov 3 that ends Nov 10."""
    close_directly(backend, hiring_manager)
    grace_directly(backend, by=hiring_manager, ends=ENDS, set_on=SET_ON, action=FLAG_OVERDUE)
    return backend


def test_extending_moves_the_end_date_writes_an_event_and_emails_nobody(
    in_grace, hiring_manager, django_capture_on_commit_callbacks, mailoutbox
):
    with django_capture_on_commit_callbacks(execute=True):
        event = extend_grace_period(
            in_grace,
            ends=date(2026, 11, 17),
            note="  Final interviews moved.  ",
            by=hiring_manager,
            today=date(2026, 11, 6),
        )

    stored = JobOpening.objects.get(pk=in_grace.pk)
    assert (stored.grace_period_ends, stored.grace_period_set_on, stored.grace_expiry_action) == (
        date(2026, 11, 17),
        date(2026, 11, 6),
        FLAG_OVERDUE,
    )
    assert (event.kind, event.by, event.note) == (
        OpeningEvent.Kind.GRACE_PERIOD_EXTENDED,
        hiring_manager,
        "Extended from Nov 10, 2026 to Nov 17, 2026. Reason: Final interviews moved.",
    )
    assert mailoutbox == []


def test_reminders_follow_the_new_end_date_after_an_extension(
    in_grace, hiring_manager, django_capture_on_commit_callbacks, mailoutbox
):
    with django_capture_on_commit_callbacks(execute=True):
        process_grace_periods(today=date(2026, 11, 7))  # the old 3-day reminder
        extend_grace_period(
            in_grace,
            ends=date(2026, 11, 17),
            note="More time.",
            by=hiring_manager,
            today=date(2026, 11, 8),
        )
        for day in range(9, 18):
            process_grace_periods(today=date(2026, 11, day))

    sent = [(m.to[0], m.subject.split(" left")[0]) for m in mailoutbox]
    assert sent == [
        ("ann@example.com", "3 days"),  # Nov 7, for the old Nov 10 end
        ("ben@example.com", "3 days"),
        ("ann@example.com", "3 days"),  # Nov 14, for the new Nov 17 end
        ("ben@example.com", "3 days"),
        ("ann@example.com", "1 day"),  # Nov 16
        ("ben@example.com", "1 day"),
        ("hal@example.com", "Backend Developer is overdue: 2 applicants still in progress"),
    ]
    assert JobOpening.objects.get(pk=in_grace.pk).grace_expired_on == date(2026, 11, 17)


@pytest.mark.parametrize("note", ["", "   "])
def test_extending_needs_a_note(in_grace, hiring_manager, note):
    before = grace_snapshot(in_grace)

    with pytest.raises(ValidationError) as refused:
        extend_grace_period(
            in_grace, ends=date(2026, 11, 17), note=note, by=hiring_manager, today=SET_ON
        )

    assert refused.value.code == NOTE_REQUIRED
    assert grace_snapshot(in_grace) == before


@pytest.mark.parametrize(
    ("today", "ends", "allowed"),
    [
        (date(2026, 11, 6), date(2026, 11, 10), False),  # the current end
        (date(2026, 11, 6), date(2026, 11, 11), True),  # the day after the current end
        (date(2026, 11, 12), date(2026, 11, 12), False),  # overdue: today isn't after today
        (date(2026, 11, 12), date(2026, 11, 13), True),
        (date(2026, 11, 6), date(2027, 2, 4), True),  # 90 days from today
        (date(2026, 11, 6), date(2027, 2, 5), False),  # 91 days
    ],
)
def test_the_new_end_is_after_the_current_end_and_today_and_within_ninety_days(
    in_grace, hiring_manager, today, ends, allowed
):
    if allowed:
        extend_grace_period(in_grace, ends=ends, note="Why.", by=hiring_manager, today=today)
        assert JobOpening.objects.get(pk=in_grace.pk).grace_period_ends == ends
        return
    with pytest.raises(ValidationError) as refused:
        extend_grace_period(in_grace, ends=ends, note="Why.", by=hiring_manager, today=today)
    assert refused.value.code == INVALID_GRACE_END
    assert JobOpening.objects.get(pk=in_grace.pk).grace_period_ends == ENDS


@pytest.mark.parametrize("user_fixture", ["recruiter", "interviewer", "no_role_user"])
def test_only_closure_deciders_can_extend(request, in_grace, user_fixture):
    before = grace_snapshot(in_grace)

    with pytest.raises(PermissionDenied):
        extend_grace_period(
            in_grace,
            ends=date(2026, 11, 17),
            note="Why.",
            by=request.getfixturevalue(user_fixture),
        )

    assert grace_snapshot(in_grace) == before


def test_extending_without_a_grace_period_is_refused(backend, hiring_manager, ending):
    close_directly(backend, hiring_manager)

    with pytest.raises(ValidationError) as refused:
        extend_grace_period(backend, ends=date(2026, 11, 17), note="Why.", by=hiring_manager)

    assert refused.value.code == NO_GRACE_PERIOD


def test_extending_an_overdue_grace_period_clears_overdue(
    in_grace, hiring_manager, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        process_grace_periods(today=ENDS)
    assert JobOpening.objects.get(pk=in_grace.pk).is_overdue

    extend_grace_period(
        in_grace,
        ends=date(2026, 11, 20),
        note="One more week.",
        by=hiring_manager,
        today=date(2026, 11, 13),
    )

    stored = JobOpening.objects.get(pk=in_grace.pk)
    assert (stored.is_overdue, stored.grace_period_running, stored.grace_expired_on) == (
        False,
        True,
        None,
    )


def test_extending_after_an_auto_cancel_ended_is_refused(
    backend, hiring_manager, ending, django_capture_on_commit_callbacks
):
    close_directly(backend, hiring_manager)
    grace_directly(backend, by=hiring_manager, ends=ENDS, set_on=SET_ON, action=AUTO_CANCEL)
    with django_capture_on_commit_callbacks(execute=True):
        process_grace_periods(today=ENDS)
    before = grace_snapshot(backend)

    with pytest.raises(ValidationError) as refused:
        extend_grace_period(
            backend,
            ends=date(2026, 11, 20),
            note="Too late.",
            by=hiring_manager,
            today=date(2026, 11, 12),
        )

    assert refused.value.code == GRACE_ALREADY_CANCELLED
    assert grace_snapshot(backend) == before


# Reminders and the end, beyond the TDD cycles


@pytest.mark.parametrize(
    ("action", "consequence"),
    [(AUTO_CANCEL, "will be closed"), (FLAG_OVERDUE, "may be closed")],
)
def test_reminder_wording_matches_the_expiry_action(
    backend,
    hiring_manager,
    ending,
    django_capture_on_commit_callbacks,
    mailoutbox,
    action,
    consequence,
):
    close_directly(backend, hiring_manager)
    grace_directly(backend, by=hiring_manager, ends=ENDS, set_on=SET_ON, action=action)

    with django_capture_on_commit_callbacks(execute=True):
        process_grace_periods(today=date(2026, 11, 9))

    words = body(mailoutbox[0])
    assert mailoutbox[0].subject == "1 day left on your application for Backend Developer"
    assert "ends on November 10, 2026, 1 day from now" in words
    assert f"your application {consequence}" in words
    assert "our team will be in touch to complete the next step" in words.lower()


def test_a_reminder_goes_only_to_those_still_in_progress_at_that_moment(
    backend, hiring_manager, ending, django_capture_on_commit_callbacks, mailoutbox
):
    close_directly(backend, hiring_manager)
    grace_directly(backend, by=hiring_manager, ends=ENDS, set_on=SET_ON, action=FLAG_OVERDUE)
    move_application(ending["Ben"], Stage.WITHDRAWN, by=hiring_manager)

    with django_capture_on_commit_callbacks(execute=True):
        run = process_grace_periods(today=date(2026, 11, 7))

    assert run.reminders_sent == 1
    assert [m.to[0] for m in mailoutbox] == ["ann@example.com"]


def test_a_three_day_grace_period_sends_only_the_one_day_reminder(
    backend, hiring_manager, ending, django_capture_on_commit_callbacks, mailoutbox
):
    close_directly(backend, hiring_manager)
    with django_capture_on_commit_callbacks(execute=True):
        set_grace_period(
            backend, days=3, action=AUTO_CANCEL, by=hiring_manager, today=date(2026, 11, 7)
        )
        for day in (7, 8, 9):
            process_grace_periods(today=date(2026, 11, day))

    kinds = sorted(CandidateMessage.objects.values_list("candidate__first_name", "kind"))
    assert kinds == [
        ("Ann", CandidateMessage.Kind.GRACE_PERIOD_SET),
        ("Ann", CandidateMessage.Kind.GRACE_REMINDER),
        ("Ben", CandidateMessage.Kind.GRACE_PERIOD_SET),
        ("Ben", CandidateMessage.Kind.GRACE_REMINDER),
    ]
    assert {m.subject for m in mailoutbox if "left" in m.subject} == {
        "1 day left on your application for Backend Developer"
    }


def test_flag_overdue_with_nobody_left_writes_the_event_but_emails_nobody(
    backend, hiring_manager, ending, django_capture_on_commit_callbacks, mailoutbox
):
    close_directly(backend, hiring_manager)
    grace_directly(backend, by=hiring_manager, ends=ENDS, set_on=SET_ON, action=FLAG_OVERDUE)
    for name in ("Ann", "Ben"):
        move_application(ending[name], Stage.WITHDRAWN, by=hiring_manager)

    with django_capture_on_commit_callbacks(execute=True):
        process_grace_periods(today=ENDS)

    event = backend.events.get(kind=OpeningEvent.Kind.GRACE_PERIOD_EXPIRED)
    assert event.note == "Ended Nov 10, 2026 with nobody still in progress. Flagged as overdue."
    assert mailoutbox == []


def test_cancel_now_during_a_grace_period_leaves_the_end_nothing_to_cancel(
    backend, hiring_manager, ending, django_capture_on_commit_callbacks, mailoutbox
):
    close_directly(backend, hiring_manager)
    grace_directly(backend, by=hiring_manager, ends=ENDS, set_on=SET_ON, action=AUTO_CANCEL)
    with django_capture_on_commit_callbacks(execute=True):
        cancel_remaining_applications(backend, by=hiring_manager)
    sent = len(mailoutbox)

    with django_capture_on_commit_callbacks(execute=True):
        run = process_grace_periods(today=ENDS)

    assert run.expired == ["Backend Developer"]
    assert backend.events.filter(kind=OpeningEvent.Kind.APPLICATIONS_CANCELLED).count() == 1
    assert len(mailoutbox) == sent


def test_the_end_is_recorded_by_the_authority_once_the_setter_can_no_longer_decide(
    backend, hiring_manager, ending, make_user, django_capture_on_commit_callbacks
):
    olive = make_user("olive", HIRING_MANAGER, first_name="Olive", last_name="Other")
    close_directly(backend, hiring_manager)
    grace_directly(backend, by=olive, ends=ENDS, set_on=SET_ON, action=AUTO_CANCEL)
    olive.is_active = False
    olive.save()

    with django_capture_on_commit_callbacks(execute=True):
        process_grace_periods(today=ENDS)

    ended = backend.events.filter(
        kind__in=[OpeningEvent.Kind.GRACE_PERIOD_EXPIRED, OpeningEvent.Kind.APPLICATIONS_CANCELLED]
    )
    assert set(ended.values_list("by__username", flat=True)) == {"manager"}


def test_an_opening_nobody_can_decide_for_is_skipped_with_a_warning_and_waits(
    skilled_opening, authority, ann, application_at, django_capture_on_commit_callbacks
):
    application_at(ann, skilled_opening, Stage.SCREENING)
    close_directly(skilled_opening, authority)
    grace_directly(skilled_opening, by=authority, ends=ENDS, set_on=SET_ON, action=AUTO_CANCEL)
    authority.is_active = False  # Riley, its Recruiter authority, has left
    authority.save()
    before = grace_snapshot(skilled_opening)

    with django_capture_on_commit_callbacks(execute=True):
        run = process_grace_periods(today=ENDS)

    assert run.expired == []
    assert run.warnings == [
        "Skipped Support Specialist: neither the person who set its grace period nor its "
        "designated authority can decide its closure any more."
    ]
    assert grace_snapshot(skilled_opening) == before


@pytest.mark.parametrize(
    "failing_write",
    [
        'UPDATE "openings_jobopening"',
        'INSERT INTO "openings_openingevent"',
        'INSERT INTO "applications_stagechange"',
    ],
)
def test_if_any_write_of_the_end_fails_none_is_kept_and_a_retry_works(
    backend,
    hiring_manager,
    ending,
    django_capture_on_commit_callbacks,
    mailoutbox,
    failing_write,
):
    close_directly(backend, hiring_manager)
    grace_directly(backend, by=hiring_manager, ends=ENDS, set_on=SET_ON, action=AUTO_CANCEL)
    before = grace_snapshot(backend)

    with (
        django_capture_on_commit_callbacks(execute=True),
        connection.execute_wrapper(FailOn(failing_write)),
        pytest.raises(DatabaseError),
    ):
        process_grace_periods(today=ENDS)

    assert grace_snapshot(backend) == before
    assert mailoutbox == []

    with django_capture_on_commit_callbacks(execute=True):
        run = process_grace_periods(today=ENDS)

    assert run.expired == ["Backend Developer"]
    assert len(mailoutbox) == 2
