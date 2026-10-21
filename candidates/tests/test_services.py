import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from applications.models import Application, StageChange
from applications.stages import Stage
from candidates.models import Candidate
from candidates.services import archive_candidate, delete_candidate

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("stage", "blocks"),
    [
        (Stage.APPLIED, True),
        (Stage.SCREENING, True),
        (Stage.INTERVIEW, True),
        (Stage.FINAL_REVIEW, True),
        (Stage.OFFER, True),
        (Stage.HIRED, False),
        (Stage.REJECTED, False),
        (Stage.WITHDRAWN, False),
    ],
)
def test_archiving_is_refused_while_any_application_is_active(
    recruiter, kai, backend, qa, application_at, stage, blocks
):
    # One finished application, which never blocks, and one at the stage under test.
    application_at(kai, qa, Stage.REJECTED)
    application_at(kai, backend, stage)

    if blocks:
        with pytest.raises(ValidationError, match="Kai Moreno has an active application"):
            archive_candidate(kai, by=recruiter)
    else:
        archive_candidate(kai, by=recruiter)

    stored = Candidate.objects.get(pk=kai.pk)
    if blocks:
        assert (stored.is_archived, stored.archived_at) == (False, None)
    else:
        assert stored.is_archived is True
        assert stored.archived_at is not None


@pytest.fixture
def staff_only(make_user):
    """Can reach the Django admin, but is no Admin: ``is_staff`` never grants deleting."""
    return make_user("staffer", is_staff=True)


@pytest.mark.parametrize(
    ("user_fixture", "allowed"),
    [
        ("admin", True),
        ("recruiter", False),
        ("hiring_manager", False),
        ("interviewer", False),
        ("no_role_user", False),
        ("staff_only", False),
    ],
)
def test_only_admins_can_permanently_delete_a_candidate(
    request, kai, backend, application_at, user_fixture, allowed
):
    application = application_at(kai, backend, Stage.REJECTED)
    user = request.getfixturevalue(user_fixture)

    if allowed:
        delete_candidate(kai, by=user)
    else:
        with pytest.raises(PermissionDenied, match="Only Admins can permanently delete"):
            delete_candidate(kai, by=user)

    remaining = (
        Candidate.objects.filter(pk=kai.pk).count(),
        Application.objects.filter(pk=application.pk).count(),
        StageChange.objects.filter(application_id=application.pk).count(),
    )
    assert remaining == ((0, 0, 0) if allowed else (1, 1, 2))
