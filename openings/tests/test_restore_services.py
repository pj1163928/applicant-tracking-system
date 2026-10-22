"""Restoring applicants after a reopening: restore_applications() and the restore list."""

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from applications.models import Application, StageChange
from applications.services import ARCHIVED_CANDIDATE
from applications.stages import Stage
from candidates.models import Candidate
from notifications.models import CandidateMessage
from openings.models import JobOpening, OpeningEvent
from openings.services import (
    NOT_OPEN,
    NOT_RESTORABLE,
    cancel_remaining_applications,
    restorable_cancellations,
    restore_applications,
    restore_choices,
)
from openings.tests.conftest import cancel_directly, close_directly, move_directly, reopen_directly

pytestmark = pytest.mark.django_db


def stage_of(application) -> str:
    return Application.objects.get(pk=application.pk).stage


def test_restore_goes_back_to_the_stage_before_the_latest_closure(
    backend, recruiter, hiring_manager, make_candidate, application_at
):
    jade = application_at(make_candidate("Jade"), backend, Stage.INTERVIEW)
    # First closure: cancelled from Interview, restored there, then moved on to Final Review.
    first = close_directly(backend, recruiter)
    cancel_directly(jade, first, recruiter)
    reopen_directly(backend, recruiter)
    move_directly(jade, Stage.INTERVIEW, hiring_manager, cause="reopening", closure=first)
    move_directly(jade, Stage.FINAL_REVIEW, hiring_manager)
    # Second closure: cancelled again, this time from Final Review.
    latest = close_directly(backend, recruiter)
    cancel_directly(jade, latest, recruiter)
    reopen_directly(backend, recruiter)

    restore_applications(backend, [jade], by=hiring_manager)

    assert stage_of(jade) == Stage.FINAL_REVIEW
    row = jade.stage_changes.last()
    assert (row.from_stage, row.to_stage, row.cause, row.closure, row.note) == (
        Stage.REJECTED,
        Stage.FINAL_REVIEW,
        StageChange.Cause.REOPENING,
        latest,
        "Position reopened.",
    )


def test_restoring_into_offer_needs_can_make_offer(
    backend, recruiter, hiring_manager, make_candidate, application_at, monkeypatch
):
    dev = application_at(make_candidate("Dev"), backend, Stage.SCREENING)
    jade = application_at(make_candidate("Jade"), backend, Stage.OFFER)
    closure = close_directly(backend, recruiter)
    cancel_directly(dev, closure, recruiter)
    cancel_directly(jade, closure, recruiter)
    reopen_directly(backend, recruiter)
    # Today everyone who may decide a closure may also make offers, so take that
    # right away for this test: the restore must still go through the offer rule.
    monkeypatch.setattr("applications.services.can_make_offer", lambda user, opening: False)
    history = StageChange.objects.count()

    with pytest.raises(PermissionDenied, match=r"^Jade Test can't be restored to Offer\. Only "):
        restore_applications(backend, [dev, jade], by=hiring_manager)

    assert (stage_of(dev), stage_of(jade)) == (Stage.REJECTED, Stage.REJECTED)
    assert StageChange.objects.count() == history


def test_archived_candidates_are_listed_but_cannot_be_restored(
    backend, recruiter, hiring_manager, make_candidate, application_at
):
    dev = application_at(make_candidate("Dev"), backend, Stage.SCREENING)
    lena = application_at(make_candidate("Lena"), backend, Stage.INTERVIEW)
    closure = close_directly(backend, recruiter)
    cancel_directly(dev, closure, recruiter)
    cancel_directly(lena, closure, recruiter)
    reopen_directly(backend, recruiter)
    Candidate.objects.filter(pk=lena.candidate_id).update(
        is_archived=True, archived_at="2026-10-21T12:00Z"
    )
    history = StageChange.objects.count()

    choices = {choice.application.pk: choice for choice in restore_choices(backend, hiring_manager)}
    assert (choices[dev.pk].selectable, choices[dev.pk].refusal) == (True, "")
    assert (choices[lena.pk].selectable, choices[lena.pk].refusal) == (
        False,
        "Archived; unarchive first",
    )
    with pytest.raises(ValidationError) as refused:
        restore_applications(backend, [dev, lena], by=hiring_manager)
    assert refused.value.code == ARCHIVED_CANDIDATE
    assert (stage_of(dev), stage_of(lena)) == (Stage.REJECTED, Stage.REJECTED)
    assert StageChange.objects.count() == history


@pytest.fixture
def reopened(backend, recruiter, make_candidate, application_at):
    """Backend Developer, closed with Dev (Screening) and Jade (Offer) cancelled, then reopened.

    Ann was at Interview and stays in progress through the closure.
    """
    dev = application_at(make_candidate("Dev"), backend, Stage.SCREENING)
    jade = application_at(make_candidate("Jade"), backend, Stage.OFFER)
    ann = application_at(make_candidate("Ann"), backend, Stage.INTERVIEW)
    closure = close_directly(backend, recruiter)
    cancel_directly(dev, closure, recruiter)
    cancel_directly(jade, closure, recruiter)
    reopen_directly(backend, recruiter)
    return {"dev": dev, "jade": jade, "ann": ann, "closure": closure}


def snapshot(opening):
    return (
        sorted(opening.applications.values_list("pk", "stage")),
        StageChange.objects.count(),
        OpeningEvent.objects.count(),
        CandidateMessage.objects.count(),
    )


def restorable_pks(opening) -> set[int]:
    return set(restorable_cancellations(opening).values_list("application_id", flat=True))


def test_the_restore_list_holds_only_applicants_cancelled_at_the_latest_closure(
    backend, recruiter, hiring_manager, make_candidate, application_at
):
    early = application_at(make_candidate("Early"), backend, Stage.SCREENING)
    late = application_at(make_candidate("Late"), backend, Stage.APPLIED)
    moved = application_at(make_candidate("Moved"), backend, Stage.INTERVIEW)
    rejected = application_at(make_candidate("Rejected"), backend, Stage.REJECTED)
    first = close_directly(backend, recruiter)
    cancel_directly(early, first, recruiter)  # cancelled at the first closure, never restored
    reopen_directly(backend, recruiter)
    latest = close_directly(backend, recruiter)
    cancel_directly(late, latest, recruiter)
    cancel_directly(moved, latest, recruiter)
    reopen_directly(backend, recruiter)
    move_directly(moved, Stage.SCREENING, hiring_manager)  # reopened by hand since

    assert restorable_pks(backend) == {late.pk}
    choices = restore_choices(backend, hiring_manager)
    assert [(c.application.pk, c.stage) for c in choices] == [(late.pk, Stage.APPLIED)]
    assert rejected.pk not in restorable_pks(backend)  # rejected by hand, not by a closure


def test_an_opening_never_closed_has_nobody_to_restore(backend, hiring_manager):
    assert restore_choices(backend, hiring_manager) == []


def test_restoring_writes_one_history_row_per_applicant_and_emails_each_once(
    backend, reopened, hiring_manager, mailoutbox, django_capture_on_commit_callbacks
):
    dev, jade = reopened["dev"], reopened["jade"]
    history = StageChange.objects.count()

    with django_capture_on_commit_callbacks(execute=True):
        rows = restore_applications(backend, [jade, dev, dev], by=hiring_manager)

    assert [(row.application_id, row.to_stage) for row in rows] == [
        (dev.pk, Stage.SCREENING),
        (jade.pk, Stage.OFFER),
    ]
    assert StageChange.objects.count() == history + 2
    assert (stage_of(dev), stage_of(jade)) == (Stage.SCREENING, Stage.OFFER)
    assert sorted(m.to[0] for m in mailoutbox) == ["dev@example.com", "jade@example.com"]
    body = " ".join(mailoutbox[0].body.split())
    assert "has reopened" in body
    assert "our team will be in touch to complete the next step" in body.lower()
    messages = CandidateMessage.objects.filter(kind=CandidateMessage.Kind.RESTORED)
    assert set(messages.values_list("application_id", "occasion")) == {
        (dev.pk, f"closure-{reopened['closure'].pk}"),
        (jade.pk, f"closure-{reopened['closure'].pk}"),
    }


def test_restoring_writes_one_event_naming_who_went_back_and_who_didnt(
    backend, reopened, hiring_manager
):
    restore_applications(backend, [reopened["dev"]], by=hiring_manager)

    event = backend.events.first()
    assert (event.kind, event.by, event.note) == (
        OpeningEvent.Kind.APPLICATIONS_RESTORED,
        hiring_manager,
        "Restored Dev Test (Screening). 1 applicant left cancelled.",
    )


def test_restoring_nobody_records_the_choice_and_changes_no_stage(
    backend, reopened, hiring_manager, mailoutbox, django_capture_on_commit_callbacks
):
    history = StageChange.objects.count()

    with django_capture_on_commit_callbacks(execute=True):
        rows = restore_applications(backend, [], by=hiring_manager)

    assert rows == []
    assert StageChange.objects.count() == history
    assert mailoutbox == []
    event = backend.events.first()
    assert (event.kind, event.note) == (
        OpeningEvent.Kind.APPLICATIONS_RESTORED,
        "Chose not to restore anyone. 2 applicants left cancelled.",
    )
    assert restorable_pks(backend) == {reopened["dev"].pk, reopened["jade"].pk}


def test_restoring_the_same_applicant_twice_is_refused_and_sends_no_second_email(
    backend, reopened, hiring_manager, mailoutbox, django_capture_on_commit_callbacks
):
    dev = reopened["dev"]
    with django_capture_on_commit_callbacks(execute=True):
        restore_applications(backend, [dev], by=hiring_manager)
    before = snapshot(backend)

    with (
        django_capture_on_commit_callbacks(execute=True),
        pytest.raises(ValidationError) as refused,
    ):
        restore_applications(backend, [dev], by=hiring_manager)

    assert refused.value.code == NOT_RESTORABLE
    assert snapshot(backend) == before
    assert len(mailoutbox) == 1


def test_an_applicant_the_closure_didnt_cancel_cant_be_restored(backend, reopened, hiring_manager):
    before = snapshot(backend)

    with pytest.raises(ValidationError, match="Ann Test wasn't cancelled") as refused:
        restore_applications(backend, [reopened["dev"], reopened["ann"]], by=hiring_manager)

    assert refused.value.code == NOT_RESTORABLE
    assert snapshot(backend) == before


@pytest.mark.parametrize("role", ["admin", "hiring_manager", "authority"])
def test_restoring_is_allowed_to_closure_deciders(
    request, skilled_opening, recruiter, make_candidate, application_at, role
):
    dev = application_at(make_candidate("Dev"), skilled_opening, Stage.SCREENING)
    closure = close_directly(skilled_opening, recruiter)
    cancel_directly(dev, closure, recruiter)
    reopen_directly(skilled_opening, recruiter)

    restore_applications(skilled_opening, [dev], by=request.getfixturevalue(role))

    assert stage_of(dev) == Stage.SCREENING


@pytest.mark.parametrize("role", ["recruiter", "interviewer", "no_role_user", "inactive_manager"])
def test_restoring_is_refused_for_everyone_else_and_writes_nothing(
    request, backend, reopened, role
):
    before = snapshot(backend)

    with pytest.raises(PermissionDenied, match="decide what happens to its applicants"):
        restore_applications(backend, [reopened["dev"]], by=request.getfixturevalue(role))

    assert snapshot(backend) == before


def test_restoring_is_refused_while_the_opening_is_closed(
    backend, recruiter, hiring_manager, make_candidate, application_at
):
    dev = application_at(make_candidate("Dev"), backend, Stage.SCREENING)
    closure = close_directly(backend, recruiter)
    cancel_directly(dev, closure, recruiter)
    before = snapshot(backend)

    with pytest.raises(ValidationError) as refused:
        restore_applications(backend, [dev], by=hiring_manager)

    assert refused.value.code == NOT_OPEN
    assert snapshot(backend) == before


def test_restore_choices_mark_offer_rows_for_users_who_cannot_make_offers(
    backend, reopened, hiring_manager, monkeypatch
):
    monkeypatch.setattr("applications.services.can_make_offer", lambda user, opening: False)

    choices = {c.application.pk: c for c in restore_choices(backend, hiring_manager)}

    assert choices[reopened["dev"].pk].selectable
    assert choices[reopened["jade"].pk].refusal == "Restoring to Offer needs offer authority"


def test_cancel_now_links_each_cancellation_to_the_closure_it_belongs_to(
    backend, hiring_manager, recruiter, make_candidate, application_at
):
    dev = application_at(make_candidate("Dev"), backend, Stage.SCREENING)
    closure = close_directly(backend, recruiter)

    rows = cancel_remaining_applications(backend, by=hiring_manager)

    assert [(row.application_id, row.closure) for row in rows] == [(dev.pk, closure)]
    assert restorable_pks(backend) == {dev.pk}
    assert JobOpening.objects.get(pk=backend.pk).status == JobOpening.Status.CLOSED
