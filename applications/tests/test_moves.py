"""``move_application()``: one history row and the new stage together, or nothing at all."""

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, connection

from accounts.roles import INTERVIEWER, RECRUITER
from applications.models import Application, StageChange
from applications.services import (
    ILLEGAL_MOVE,
    NOTE_REQUIRED,
    STALE_STAGE,
    move_application,
)
from applications.stages import Stage
from candidates.models import Candidate

pytestmark = pytest.mark.django_db


def put_at(application: Application, stage: str) -> None:
    """Set up a starting stage directly, without the service under test, keeping history in step."""
    StageChange.objects.create(
        application=application,
        from_stage=application.stage,
        to_stage=stage,
        changed_by=application.opening.designated_authority,
        note="Test setup.",
    )
    Application.objects.filter(pk=application.pk).update(stage=stage)
    application.stage = stage


def stored(application: Application) -> tuple[str, int]:
    """The stage in the database and the number of history rows: what a refusal must not change."""
    fresh = Application.objects.get(pk=application.pk)
    return fresh.stage, fresh.stage_changes.count()


def candidate(first_name: str) -> Candidate:
    return Candidate.objects.create(
        first_name=first_name, last_name="Test", email=f"{first_name.lower()}@example.com"
    )


@pytest.fixture
def app(apply, ann, backend, indeed) -> Application:
    """Ann's application for Backend Developer, whose authority is Hal (a Hiring Manager)."""
    return apply(ann, backend, indeed)


def test_a_successful_move_writes_exactly_one_history_row_and_updates_the_stage(app, recruiter):
    before = StageChange.objects.count()

    row = move_application(app, Stage.SCREENING, by=recruiter)

    assert StageChange.objects.count() == before + 1
    assert stored(app) == (Stage.SCREENING, 2)
    assert app.stage == Stage.SCREENING  # the caller's copy is updated too
    assert row == app.stage_changes.last()
    assert (row.from_stage, row.to_stage, row.changed_by) == (
        Stage.APPLIED,
        Stage.SCREENING,
        recruiter,
    )
    assert (row.note, row.cause) == ("", StageChange.Cause.MANUAL)
    assert row.changed_at is not None


def test_a_move_keeps_its_note(app, recruiter):
    row = move_application(app, Stage.INTERVIEW, by=recruiter, note="  Strong portfolio.  ")

    assert stored(app) == (Stage.INTERVIEW, 2)
    assert row.note == "Strong portfolio."


@pytest.mark.parametrize(
    ("start", "to", "user_fixture", "note", "refusal", "code"),
    [
        # Moves the transitions table refuses.
        (Stage.SCREENING, Stage.SCREENING, "admin", "Again.", ValidationError, ILLEGAL_MOVE),
        (Stage.APPLIED, Stage.HIRED, "admin", "Straight to hired.", ValidationError, ILLEGAL_MOVE),
        (Stage.HIRED, Stage.REJECTED, "admin", "Undo the hire.", ValidationError, ILLEGAL_MOVE),
        (Stage.REJECTED, Stage.WITHDRAWN, "admin", "Switch.", ValidationError, ILLEGAL_MOVE),
        (Stage.APPLIED, "promoted", "admin", "No such stage.", ValidationError, ILLEGAL_MOVE),
        # A required note that is missing or blank.
        (Stage.APPLIED, Stage.INTERVIEW, "admin", "", ValidationError, NOTE_REQUIRED),
        (Stage.INTERVIEW, Stage.SCREENING, "admin", "   ", ValidationError, NOTE_REQUIRED),
        (Stage.REJECTED, Stage.APPLIED, "admin", "", ValidationError, NOTE_REQUIRED),
        # Users who may not move stages at all.
        (Stage.APPLIED, Stage.SCREENING, "interviewer", "", PermissionDenied, None),
        (Stage.APPLIED, Stage.SCREENING, "no_role_user", "", PermissionDenied, None),
        # A Recruiter who is not this opening's authority, moving into Offer or Hired.
        (Stage.FINAL_REVIEW, Stage.OFFER, "recruiter", "", PermissionDenied, None),
        (Stage.OFFER, Stage.HIRED, "recruiter", "", PermissionDenied, None),
    ],
)
def test_a_refused_move_leaves_the_stage_and_history_unchanged(
    request, app, start, to, user_fixture, note, refusal, code
):
    if start != Stage.APPLIED:
        put_at(app, start)
    before = stored(app)

    with pytest.raises(refusal) as refused:
        move_application(app, to, by=request.getfixturevalue(user_fixture), note=note)

    if code is not None:
        assert refused.value.code == code
    assert stored(app) == before
    assert app.stage == start


@pytest.fixture
def riley(make_user):
    """A Recruiter who is the designated authority of the Support Specialist opening."""
    return make_user("riley", RECRUITER, first_name="Riley", last_name="Chen")


@pytest.fixture
def staff_recruiter(make_user):
    """A Recruiter who can log in to the Django admin, which is not the Admin role."""
    return make_user("staff-recruiter", RECRUITER, is_staff=True)


@pytest.fixture
def riley_inactive(riley):
    riley.is_active = False
    riley.save()
    return riley


@pytest.fixture
def riley_now_interviewer(riley):
    riley.groups.set([Group.objects.get(name=INTERVIEWER)])
    return riley


@pytest.mark.parametrize(
    ("user_fixture", "allowed"),
    [
        ("admin", True),
        ("hiring_manager", True),
        ("riley", True),  # the opening's designated authority
        ("recruiter", False),
        ("staff_recruiter", False),
        ("interviewer", False),
        ("no_role_user", False),
        ("riley_inactive", False),
        ("riley_now_interviewer", False),
    ],
)
def test_offer_and_hired_follow_the_same_authority_rule(
    request, user_fixture, allowed, apply, make_opening, riley, indeed
):
    support = make_opening("Support Specialist", riley)
    to_offer = apply(candidate("Cy"), support, indeed)
    to_hired = apply(candidate("Di"), support, indeed)
    put_at(to_offer, Stage.FINAL_REVIEW)
    put_at(to_hired, Stage.FINAL_REVIEW)
    put_at(to_hired, Stage.OFFER)
    user = request.getfixturevalue(user_fixture)

    def outcome(application, to):
        try:
            move_application(application, to, by=user)
        except PermissionDenied:
            return False
        return True

    assert (outcome(to_offer, Stage.OFFER), outcome(to_hired, Stage.HIRED)) == (allowed, allowed)
    expected = (Stage.OFFER, Stage.HIRED) if allowed else (Stage.FINAL_REVIEW, Stage.OFFER)
    assert (stored(to_offer)[0], stored(to_hired)[0]) == expected


def test_a_stale_card_cannot_overwrite_a_newer_stage(app, recruiter, hiring_manager):
    card = Application.objects.get(pk=app.pk)  # the board loaded while Ann was at Applied
    put_at(app, Stage.FINAL_REVIEW)  # then someone else moved her on
    before = stored(app)

    with pytest.raises(ValidationError) as refused:
        move_application(card, Stage.REJECTED, by=recruiter, expected_stage=Stage.APPLIED)

    assert refused.value.code == STALE_STAGE
    assert stored(app) == before


def test_the_rules_judge_the_stored_stage_not_the_callers_copy(app, recruiter):
    card = Application.objects.get(pk=app.pk)  # still says Applied
    put_at(app, Stage.FINAL_REVIEW)

    # One step on from Applied, but backward from Final Review, so it needs a note.
    with pytest.raises(ValidationError) as refused:
        move_application(card, Stage.SCREENING, by=recruiter)

    assert refused.value.code == NOTE_REQUIRED
    assert stored(app) == (Stage.FINAL_REVIEW, 2)


@pytest.mark.parametrize("from_the_card", [True, False])
def test_submitting_the_same_move_twice_moves_once(app, recruiter, from_the_card):
    expected = Stage.APPLIED if from_the_card else None
    move_application(app, Stage.SCREENING, by=recruiter, expected_stage=expected)
    resubmitted = Application.objects.get(pk=app.pk)

    with pytest.raises(ValidationError) as refused:
        move_application(resubmitted, Stage.SCREENING, by=recruiter, expected_stage=expected)

    assert refused.value.code == (STALE_STAGE if from_the_card else ILLEGAL_MOVE)
    assert stored(app) == (Stage.SCREENING, 2)


class FailOn:
    """Make the database refuse any statement that contains ``fragment``."""

    def __init__(self, fragment: str) -> None:
        self.fragment = fragment

    def __call__(self, execute, sql, params, many, context):
        if self.fragment in sql:
            raise DatabaseError("disk full")
        return execute(sql, params, many, context)


@pytest.mark.parametrize(
    "failing_write",
    ['INSERT INTO "applications_stagechange"', 'UPDATE "applications_application"'],
)
def test_if_either_write_fails_neither_is_kept(app, recruiter, failing_write):
    with connection.execute_wrapper(FailOn(failing_write)), pytest.raises(DatabaseError):
        move_application(app, Stage.SCREENING, by=recruiter)

    assert stored(app) == (Stage.APPLIED, 1)
