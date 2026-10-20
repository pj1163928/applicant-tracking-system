import pytest
from django.contrib.auth.models import AnonymousUser

from accounts.permissions import can_manage_candidates

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("user_fixture", "expected"),
    [
        ("admin", True),
        ("recruiter", True),
        ("hiring_manager", False),
        ("interviewer", False),
        ("no_role_user", False),
    ],
)
def test_can_manage_candidates_by_role(request, user_fixture, expected):
    assert can_manage_candidates(request.getfixturevalue(user_fixture)) is expected


def test_inactive_recruiter_cannot_manage_candidates(recruiter):
    recruiter.is_active = False

    assert can_manage_candidates(recruiter) is False


def test_anonymous_user_cannot_manage_candidates():
    assert can_manage_candidates(AnonymousUser()) is False
