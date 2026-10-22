"""change_authority(): handing an opening to a new designated authority."""

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from accounts.roles import RECRUITER
from applications.services import record_application
from candidates.models import Candidate, Source
from notifications.attention import attention_count
from openings.models import JobOpening, OpeningEvent
from openings.services import INELIGIBLE_AUTHORITY, SAME_AUTHORITY, change_authority

pytestmark = pytest.mark.django_db


@pytest.fixture
def opening(make_opening, hiring_manager) -> JobOpening:
    return make_opening("Backend Developer", hiring_manager)


@pytest.fixture
def inactive_recruiter(make_user):
    return make_user("gone", RECRUITER, first_name="Gil", last_name="Gone", is_active=False)


@pytest.mark.parametrize("new_authority", ["interviewer", "no_role_user", "inactive_recruiter"])
def test_change_authority_refuses_an_ineligible_new_authority_and_writes_nothing(
    request,
    opening,
    admin,
    hiring_manager,
    new_authority,
    mailoutbox,
    django_capture_on_commit_callbacks,
):
    to = request.getfixturevalue(new_authority)

    with (
        django_capture_on_commit_callbacks(execute=True),
        pytest.raises(ValidationError) as refused,
    ):
        change_authority(opening, to=to, by=admin)

    assert refused.value.code == INELIGIBLE_AUTHORITY
    assert JobOpening.objects.get(pk=opening.pk).designated_authority == hiring_manager
    assert not OpeningEvent.objects.filter(opening=opening).exists()
    assert mailoutbox == []


@pytest.fixture
def morgan(make_user):
    return make_user(
        "morgan", RECRUITER, first_name="Morgan", last_name="Patel", email="morgan@example.com"
    )


@pytest.mark.parametrize("by", ["admin", "recruiter"])
def test_admins_and_recruiters_change_the_authority_with_an_event_and_one_email(
    request, opening, morgan, by, mailoutbox, django_capture_on_commit_callbacks
):
    by = request.getfixturevalue(by)

    with django_capture_on_commit_callbacks(execute=True):
        event = change_authority(opening, to=morgan, by=by, note="  Morgan leads hiring now. ")

    assert JobOpening.objects.get(pk=opening.pk).designated_authority == morgan
    assert opening.designated_authority == morgan  # the caller's copy is updated too
    assert event.kind == OpeningEvent.Kind.AUTHORITY_CHANGED
    assert event.by == by
    assert event.note == "From Hal Manager to Morgan Patel.\nReason: Morgan leads hiring now."
    assert [m.to for m in mailoutbox] == [["morgan@example.com"]]
    assert "designated authority for Backend Developer" in mailoutbox[0].subject
    body = " ".join(mailoutbox[0].body.split())
    assert "taking over from Hal Manager" in body
    assert 'Their note: "Morgan leads hiring now."' in body


def test_an_authority_change_without_a_note_says_only_who_from_and_to(opening, admin, morgan):
    event = change_authority(opening, to=morgan, by=admin)

    assert event.note == "From Hal Manager to Morgan Patel."


@pytest.mark.parametrize("by", ["hiring_manager", "interviewer", "no_role_user"])
def test_other_roles_cannot_change_the_authority(
    request, opening, morgan, hiring_manager, by, mailoutbox, django_capture_on_commit_callbacks
):
    with (
        django_capture_on_commit_callbacks(execute=True),
        pytest.raises(PermissionDenied),
    ):
        change_authority(opening, to=morgan, by=request.getfixturevalue(by))

    assert JobOpening.objects.get(pk=opening.pk).designated_authority == hiring_manager
    assert not OpeningEvent.objects.exists()
    assert mailoutbox == []


def test_picking_the_current_authority_again_is_refused(opening, admin, hiring_manager):
    with pytest.raises(ValidationError) as refused:
        change_authority(opening, to=hiring_manager, by=admin)

    assert refused.value.code == SAME_AUTHORITY
    assert not OpeningEvent.objects.exists()


def test_a_closed_openings_waiting_decision_moves_to_the_new_authority(
    opening, admin, hiring_manager, morgan
):
    candidate = Candidate.objects.create(first_name="Ann", last_name="Lee", email="ann@x.com")
    source = Source.objects.create(name="Indeed", category=Source.Category.JOB_BOARD)
    record_application(candidate=candidate, opening=opening, source=source, by=admin)
    JobOpening.objects.filter(pk=opening.pk).update(status=JobOpening.Status.CLOSED)
    opening.refresh_from_db()
    assert attention_count(hiring_manager) == 1

    change_authority(opening, to=morgan, by=admin)

    assert attention_count(hiring_manager) == 0
    assert attention_count(morgan) == 1


def test_a_new_authority_without_an_email_address_is_still_assigned(
    opening, admin, recruiter, mailoutbox, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        change_authority(opening, to=recruiter, by=admin)

    assert JobOpening.objects.get(pk=opening.pk).designated_authority == recruiter
    assert mailoutbox == []
