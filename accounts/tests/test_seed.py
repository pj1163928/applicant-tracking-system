import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from accounts.management.commands.seed import SEED_PASSWORD
from accounts.roles import role_label

pytestmark = pytest.mark.django_db

EXPECTED_ROLES = {
    "admin": "Admin",
    "recruiter": "Recruiter",
    "manager": "Hiring Manager",
    "interviewer": "Interviewer",
}


def snapshot():
    return [
        (u.pk, u.username, u.password, u.first_name, u.is_superuser, role_label(u))
        for u in User.objects.order_by("username")
    ]


def test_seed_creates_one_user_per_role():
    call_command("seed")

    users = {u.username: u for u in User.objects.all()}
    assert {name: role_label(u) for name, u in users.items()} == EXPECTED_ROLES
    assert all(u.check_password(SEED_PASSWORD) for u in users.values())
    assert users["admin"].is_staff and users["admin"].is_superuser


def test_running_seed_twice_changes_nothing():
    call_command("seed")
    first = snapshot()

    call_command("seed")

    assert snapshot() == first


def test_seed_repairs_a_changed_seed_user():
    call_command("seed")
    user = User.objects.get(username="recruiter")
    user.set_password("something-else")
    user.groups.clear()
    user.save()

    call_command("seed")

    user.refresh_from_db()
    assert user.check_password(SEED_PASSWORD)
    assert role_label(user) == "Recruiter"
