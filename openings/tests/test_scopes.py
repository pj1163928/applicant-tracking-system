import pytest
from django.contrib.auth.models import Group

from accounts.roles import HIRING_MANAGER
from openings.scopes import ALL, MINE, default_scope, resolve_scope

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_in_hiring_manager_group(admin):
    # An Admin passes every role check, so this must still default like an Admin.
    admin.groups.add(Group.objects.get(name=HIRING_MANAGER))
    return admin


@pytest.mark.parametrize(
    ("user_fixture", "expected"),
    [
        ("hiring_manager", MINE),
        ("admin", ALL),
        ("admin_in_hiring_manager_group", ALL),
        ("recruiter", ALL),
        ("interviewer", ALL),
        ("no_role_user", ALL),
    ],
)
def test_hiring_managers_default_to_my_openings_and_everyone_else_to_all(
    request, user_fixture, expected
):
    assert default_scope(request.getfixturevalue(user_fixture)) == expected


@pytest.mark.parametrize("requested", [MINE, ALL])
def test_a_valid_requested_scope_is_kept_whatever_the_role(recruiter, hiring_manager, requested):
    assert resolve_scope(recruiter, requested) == requested
    assert resolve_scope(hiring_manager, requested) == requested


@pytest.mark.parametrize("requested", [None, "", "everything", "MINE"])
def test_a_missing_or_unknown_scope_falls_back_to_the_default(recruiter, hiring_manager, requested):
    assert resolve_scope(recruiter, requested) == ALL
    assert resolve_scope(hiring_manager, requested) == MINE
