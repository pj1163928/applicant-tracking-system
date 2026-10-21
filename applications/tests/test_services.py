from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError
from django.utils import timezone

from applications.models import Application, StageChange
from applications.services import prefill_source, record_application
from applications.stages import Stage
from candidates.models import Candidate

pytestmark = pytest.mark.django_db


def counts() -> tuple[int, int]:
    return Application.objects.count(), StageChange.objects.count()


def test_a_closed_opening_takes_no_new_applications(ann, closed_opening, indeed, recruiter):
    with pytest.raises(ValidationError) as refused:
        record_application(candidate=ann, opening=closed_opening, source=indeed, by=recruiter)

    assert refused.value.messages == ["UX Researcher is closed, so it can't take new applications."]
    assert counts() == (0, 0)


def test_an_archived_candidate_takes_no_new_applications_until_unarchived(
    ann, backend, indeed, recruiter
):
    # Archived in the database behind the caller's back: `ann` is now a stale copy.
    Candidate.objects.filter(pk=ann.pk).update(is_archived=True, archived_at=timezone.now())

    with pytest.raises(ValidationError) as refused:
        record_application(candidate=ann, opening=backend, source=indeed, by=recruiter)

    assert refused.value.messages == [
        "Ann Lee is archived, so they can't apply for anything. Unarchive them first."
    ]
    assert counts() == (0, 0)

    Candidate.objects.filter(pk=ann.pk).update(is_archived=False, archived_at=None)
    record_application(candidate=ann, opening=backend, source=indeed, by=recruiter)
    assert counts() == (1, 1)


def test_recording_an_application_writes_it_at_applied_with_exactly_one_history_row(
    ann, backend, indeed, recruiter
):
    application = record_application(candidate=ann, opening=backend, source=indeed, by=recruiter)

    assert application.stage == Stage.APPLIED
    assert counts() == (1, 1)
    first = application.stage_changes.get()
    assert (first.from_stage, first.to_stage) == ("", Stage.APPLIED)
    assert first.changed_by == recruiter
    assert first.cause == StageChange.Cause.MANUAL
    assert first.note == ""
    assert first.changed_at is not None


def test_if_the_history_row_fails_the_application_is_rolled_back_too(
    monkeypatch, ann, backend, indeed, recruiter
):
    def fail(**kwargs):
        raise DatabaseError("disk full")

    monkeypatch.setattr(StageChange.objects, "create", fail)

    with pytest.raises(DatabaseError):
        record_application(candidate=ann, opening=backend, source=indeed, by=recruiter)

    assert counts() == (0, 0)


def test_the_service_refuses_a_second_application_for_the_same_opening(
    apply, ann, backend, indeed, linkedin
):
    apply(ann, backend, indeed)

    with pytest.raises(ValidationError) as refused:
        apply(ann, backend, linkedin)

    assert refused.value.messages == ["Ann Lee has already applied for Backend Developer."]
    assert counts() == (1, 1)


def test_the_service_refuses_a_retired_source(apply, ann, backend, monster):
    with pytest.raises(ValidationError) as refused:
        apply(ann, backend, monster)

    assert refused.value.messages == ["Monster is retired, so new applications can't pick it."]
    assert counts() == (0, 0)


@pytest.mark.parametrize("user_fixture", ["hiring_manager", "interviewer", "no_role_user"])
def test_only_recruiters_and_admins_can_record_applications_through_the_service(
    request, user_fixture, ann, backend, indeed
):
    with pytest.raises(PermissionDenied):
        record_application(
            candidate=ann, opening=backend, source=indeed, by=request.getfixturevalue(user_fixture)
        )

    assert counts() == (0, 0)


def test_an_admin_can_record_an_application(ann, backend, indeed, admin):
    application = record_application(candidate=ann, opening=backend, source=indeed, by=admin)

    assert application.stage_changes.get().changed_by == admin


PREFILL_CASES = {
    # case: (Ann's earlier applications as (opening, source, days ago), in pk order; expected)
    "no earlier application": ([], None),
    "one earlier application": ([("backend", "indeed", 5)], "indeed"),
    "several: the newest by date wins, not the highest pk": (
        [("backend", "indeed", 30), ("closed", "linkedin", 2), ("qa", "referral", 10)],
        "linkedin",
    ),
    "same date: the later one wins": (
        [("backend", "indeed", 5), ("qa", "linkedin", 5)],
        "linkedin",
    ),
    "the newest source is retired: nothing": (
        [("backend", "indeed", 10), ("qa", "monster", 1)],
        None,
    ),
}


@pytest.mark.parametrize(("history", "expected"), PREFILL_CASES.values(), ids=PREFILL_CASES)
def test_the_source_is_prefilled_from_the_candidates_most_recent_application(
    request, history, expected, ann, ben, backend, qa, closed_opening, referral
):
    now = timezone.now()
    openings = {"backend": backend, "qa": qa, "closed": closed_opening}
    for opening, source, days_ago in history:
        # Built directly, not through the service, to set up the past: an opening
        # that has closed since, and a source that has been retired since.
        application = Application.objects.create(
            candidate=ann, opening=openings[opening], source=request.getfixturevalue(source)
        )
        Application.objects.filter(pk=application.pk).update(
            created_at=now - timedelta(days=days_ago)
        )
    # Someone else's newer application never counts toward Ann's pre-fill.
    Application.objects.create(candidate=ben, opening=backend, source=referral)

    wanted = request.getfixturevalue(expected) if expected else None
    assert prefill_source(ann) == wanted
