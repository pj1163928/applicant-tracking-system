import pytest
from django.contrib.auth.models import AnonymousUser

from accounts.roles import (
    HIRING_MANAGER,
    INTERVIEWER,
    RECRUITER,
    can_make_changes,
    has_role,
    is_admin,
    role_label,
)

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("user_fixture", "label", "can_change"),
    [
        ("admin", "Admin", True),
        ("recruiter", RECRUITER, True),
        ("hiring_manager", HIRING_MANAGER, True),
        ("interviewer", INTERVIEWER, False),
        ("no_role_user", "No role", False),
    ],
)
def test_role_label_and_can_make_changes(request, user_fixture, label, can_change):
    user = request.getfixturevalue(user_fixture)

    assert role_label(user) == label
    assert can_make_changes(user) is can_change


def test_admin_passes_every_role_check(admin):
    assert is_admin(admin)
    assert has_role(admin, RECRUITER)
    assert has_role(admin, INTERVIEWER)


def test_has_role_matches_only_the_named_groups(recruiter):
    assert has_role(recruiter, RECRUITER)
    assert has_role(recruiter, RECRUITER, HIRING_MANAGER)
    assert not has_role(recruiter, HIRING_MANAGER)


def test_inactive_users_fail_every_check(make_user):
    user = make_user("gone", RECRUITER, is_active=False)

    assert not has_role(user, RECRUITER)
    assert not can_make_changes(user)


def test_inactive_superuser_is_not_admin(make_user):
    user = make_user("gone", is_superuser=True, is_active=False)

    assert not is_admin(user)
    assert not has_role(user, RECRUITER)


def test_anonymous_user_has_no_role():
    anonymous = AnonymousUser()

    assert not is_admin(anonymous)
    assert not has_role(anonymous, RECRUITER)
    assert not can_make_changes(anonymous)
    assert role_label(anonymous) == ""
