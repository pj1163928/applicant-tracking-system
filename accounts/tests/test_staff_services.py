"""deactivate_staff(): a departing staff member's openings are all reassigned, then they are
deactivated, all together or not at all."""

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, connection
from django.urls import reverse

from accounts.permissions import eligible_authorities
from accounts.roles import RECRUITER
from accounts.services import (
    ALREADY_INACTIVE,
    MISSING_REASSIGNMENT,
    SELF_DEACTIVATION,
    UNEXPECTED_REASSIGNMENT,
    deactivate_staff,
)
from notifications.models import CandidateMessage
from openings.models import JobOpening, OpeningEvent
from openings.services import INELIGIBLE_AUTHORITY

pytestmark = pytest.mark.django_db


class FailOn:
    """Make the database refuse a statement containing ``fragment``, after letting ``skip`` pass."""

    def __init__(self, fragment: str, skip: int = 0) -> None:
        self.fragment = fragment
        self.skip = skip

    def __call__(self, execute, sql, params, many, context):
        if self.fragment in sql:
            if self.skip == 0:
                raise DatabaseError("disk full")
            self.skip -= 1
        return execute(sql, params, many, context)


@pytest.fixture
def departing(make_user) -> User:
    return make_user(
        "dana", RECRUITER, first_name="Dana", last_name="Departing", email="dana@example.com"
    )


@pytest.fixture
def openings(make_opening, departing) -> list[JobOpening]:
    return [
        make_opening("Backend Developer", departing),
        make_opening("QA Analyst", departing, status=JobOpening.Status.CLOSED),
    ]


# Real commits, so anything the service fails to roll back stays visible, and an email sent
# by a committed step lands in the outbox at once. serialized_rollback brings back the
# role groups (a data migration) that each real-commit test empties out.
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
@pytest.mark.parametrize(
    ("failure", "error"),
    [
        pytest.param(None, ValidationError, id="an-opening-left-without-a-new-authority"),
        pytest.param(
            FailOn('UPDATE "openings_jobopening"', skip=1),
            DatabaseError,
            id="the-second-reassignment-fails",
        ),
        pytest.param(
            FailOn('INSERT INTO "openings_openingevent"', skip=1),
            DatabaseError,
            id="the-second-event-fails",
        ),
        pytest.param(FailOn('UPDATE "auth_user"'), DatabaseError, id="the-deactivation-fails"),
    ],
)
def test_deactivate_staff_keeps_nothing_unless_every_opening_is_reassigned_and_all_writes_succeed(
    departing, openings, admin, hiring_manager, failure, error, mailoutbox
):
    backend, qa = openings
    reassignments = {backend: hiring_manager, qa: admin}
    if failure is None:
        del reassignments[qa]  # QA Analyst would be left with an inactive authority

    with pytest.raises(error):
        if failure is None:
            deactivate_staff(departing, reassignments, by=admin)
        else:
            with connection.execute_wrapper(failure):
                deactivate_staff(departing, reassignments, by=admin)

    assert User.objects.get(pk=departing.pk).is_active is True
    assert set(
        JobOpening.objects.filter(pk__in=[backend.pk, qa.pk]).values_list(
            "designated_authority", flat=True
        )
    ) == {departing.pk}
    assert not OpeningEvent.objects.filter(kind=OpeningEvent.Kind.AUTHORITY_CHANGED).exists()
    assert not CandidateMessage.objects.exists()
    assert mailoutbox == []


@pytest.fixture
def inactive_recruiter(make_user) -> User:
    return make_user("gone", RECRUITER, first_name="Gil", last_name="Gone", is_active=False)


@pytest.fixture
def stale_recruiter(make_user) -> User:
    """Active when the form was loaded, deactivated in the database since."""
    user = make_user("stale", RECRUITER, first_name="Sam", last_name="Stale")
    User.objects.filter(pk=user.pk).update(is_active=False)
    return user  # this copy still says is_active=True


@pytest.mark.parametrize(
    "new_authority",
    ["interviewer", "no_role_user", "inactive_recruiter", "stale_recruiter", "departing"],
)
def test_deactivate_staff_refuses_an_ineligible_new_authority_and_writes_nothing(
    request,
    departing,
    openings,
    admin,
    hiring_manager,
    new_authority,
    mailoutbox,
    django_capture_on_commit_callbacks,
):
    backend, qa = openings
    to = request.getfixturevalue(new_authority)

    with (
        django_capture_on_commit_callbacks(execute=True),
        pytest.raises(ValidationError) as refused,
    ):
        deactivate_staff(departing, {backend: hiring_manager, qa: to}, by=admin)

    assert refused.value.code == INELIGIBLE_AUTHORITY
    assert "QA Analyst" in refused.value.messages[0]
    assert User.objects.get(pk=departing.pk).is_active is True
    assert not OpeningEvent.objects.exists()
    assert set(JobOpening.objects.values_list("designated_authority", flat=True)) == {departing.pk}
    assert mailoutbox == []


def test_deactivate_staff_hands_every_opening_over_then_deactivates(
    departing, openings, admin, make_user, mailoutbox, django_capture_on_commit_callbacks
):
    backend, qa = openings
    morgan = make_user(
        "morgan", RECRUITER, first_name="Morgan", last_name="Patel", email="morgan@example.com"
    )

    with django_capture_on_commit_callbacks(execute=True):
        events = deactivate_staff(departing, {backend: morgan, qa: admin}, by=admin)

    assert departing.is_active is False
    assert User.objects.get(pk=departing.pk).is_active is False
    assert JobOpening.objects.get(pk=backend.pk).designated_authority == morgan
    assert JobOpening.objects.get(pk=qa.pk).designated_authority == admin
    assert [(e.opening_id, e.kind, e.by) for e in events] == [
        (backend.pk, OpeningEvent.Kind.AUTHORITY_CHANGED, admin),
        (qa.pk, OpeningEvent.Kind.AUTHORITY_CHANGED, admin),
    ]
    assert events[0].note == (
        "From Dana Departing to Morgan Patel.\n"
        "Reason: Dana Departing is leaving, so their openings were handed over."
    )
    # One email per opening, to each new authority that has an address (the admin fixture has none).
    assert [m.to for m in mailoutbox] == [["morgan@example.com"]]


def test_someone_with_no_openings_is_deactivated_with_no_reassignments(admin, interviewer):
    assert deactivate_staff(interviewer, {}, by=admin) == []

    assert User.objects.get(pk=interviewer.pk).is_active is False


@pytest.mark.parametrize("by", ["recruiter", "hiring_manager", "interviewer"])
def test_only_admins_can_deactivate_staff(request, departing, openings, admin, by):
    backend, qa = openings

    with pytest.raises(PermissionDenied):
        deactivate_staff(departing, {backend: admin, qa: admin}, by=request.getfixturevalue(by))

    assert User.objects.get(pk=departing.pk).is_active is True
    assert not OpeningEvent.objects.exists()


def test_admins_cannot_deactivate_themselves(admin, make_user):
    other_admin = make_user("admin2", is_superuser=True)
    opening = JobOpening.objects.create(
        title="Ops", department="Ops", description="x", designated_authority=admin
    )

    with pytest.raises(ValidationError) as refused:
        deactivate_staff(admin, {opening: other_admin}, by=admin)

    assert refused.value.code == SELF_DEACTIVATION
    assert User.objects.get(pk=admin.pk).is_active is True


def test_someone_already_inactive_is_refused(admin, make_user):
    gone = make_user("gone", RECRUITER, is_active=False)

    with pytest.raises(ValidationError) as refused:
        deactivate_staff(gone, {}, by=admin)

    assert refused.value.code == ALREADY_INACTIVE


def test_an_opening_someone_else_is_responsible_for_cannot_be_reassigned_here(
    departing, openings, admin, hiring_manager, make_opening
):
    backend, qa = openings
    other = make_opening("Data Engineer", hiring_manager)

    with pytest.raises(ValidationError) as refused:
        deactivate_staff(departing, {backend: admin, qa: admin, other: admin}, by=admin)

    assert refused.value.code == UNEXPECTED_REASSIGNMENT
    assert JobOpening.objects.get(pk=other.pk).designated_authority == hiring_manager
    assert User.objects.get(pk=departing.pk).is_active is True


def test_a_missing_reassignment_names_the_opening_left_without_one(departing, openings, admin):
    backend, _qa = openings

    with pytest.raises(ValidationError) as refused:
        deactivate_staff(departing, {backend: admin}, by=admin)

    assert refused.value.code == MISSING_REASSIGNMENT
    assert refused.value.messages == [
        "Pick a new designated authority for QA Analyst before deactivating Dana Departing."
    ]


def test_a_deactivated_person_cannot_log_in_and_their_session_stops_working(
    client, departing, admin
):
    client.force_login(departing)
    assert client.get(reverse("accounts:home")).status_code == 200

    deactivate_staff(departing, {}, by=admin)

    assert client.get(reverse("accounts:home")).status_code == 302
    assert client.login(username="dana", password="pw") is False


def test_a_deactivated_person_is_no_longer_an_authority_choice(departing, admin):
    assert departing in eligible_authorities()

    deactivate_staff(departing, {}, by=admin)

    assert departing not in eligible_authorities()
