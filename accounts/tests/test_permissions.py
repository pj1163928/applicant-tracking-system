import pytest
from django.contrib.auth.models import AnonymousUser, Group

from accounts.permissions import (
    can_be_designated_authority,
    can_manage_candidates,
    can_manage_openings,
    can_manage_sources,
    eligible_authorities,
)
from accounts.roles import HIRING_MANAGER, RECRUITER

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
def test_can_manage_sources_by_role(request, user_fixture, expected):
    assert can_manage_sources(request.getfixturevalue(user_fixture)) is expected


def test_inactive_or_anonymous_users_cannot_manage_sources(recruiter):
    recruiter.is_active = False

    assert can_manage_sources(recruiter) is False
    assert can_manage_sources(AnonymousUser()) is False


@pytest.fixture
def inactive_manager(make_user):
    return make_user("gone-manager", HIRING_MANAGER, is_active=False)


@pytest.fixture
def inactive_admin(make_user):
    return make_user("gone-admin", is_superuser=True, is_active=False)


@pytest.mark.parametrize(
    ("user_fixture", "eligible"),
    [
        ("admin", True),
        ("recruiter", True),
        ("hiring_manager", True),
        ("interviewer", False),
        ("no_role_user", False),
        ("inactive_manager", False),
        ("inactive_admin", False),
    ],
)
def test_only_active_admins_recruiters_and_hiring_managers_can_be_designated_authority(
    request, user_fixture, eligible
):
    user = request.getfixturevalue(user_fixture)

    assert can_be_designated_authority(user) is eligible
    # The picker's list agrees with the rule, so the form can only offer and accept eligible staff.
    assert eligible_authorities().filter(pk=user.pk).exists() is eligible


def test_anonymous_user_cannot_be_designated_authority():
    assert can_be_designated_authority(AnonymousUser()) is False


def test_eligible_authorities_lists_a_user_in_two_groups_once(make_user):
    both = make_user("both", RECRUITER)
    both.groups.add(Group.objects.get(name=HIRING_MANAGER))

    assert list(eligible_authorities()) == [both]


@pytest.mark.parametrize(
    ("user_fixture", "expected"),
    [
        ("admin", True),
        ("recruiter", True),
        ("hiring_manager", True),
        ("interviewer", False),
        ("no_role_user", False),
    ],
)
def test_can_manage_openings_by_role(request, user_fixture, expected):
    assert can_manage_openings(request.getfixturevalue(user_fixture)) is expected


def test_inactive_or_anonymous_users_cannot_manage_openings(hiring_manager):
    hiring_manager.is_active = False

    assert can_manage_openings(hiring_manager) is False
    assert can_manage_openings(AnonymousUser()) is False
