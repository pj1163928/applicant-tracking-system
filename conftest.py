"""Fixtures shared by every app's tests: one user per role."""

import pytest
from django.contrib.auth.models import Group, User

from accounts.roles import HIRING_MANAGER, INTERVIEWER, RECRUITER


@pytest.fixture(autouse=True)
def fast_password_hashing(settings):
    """Hash passwords with fast MD5 in tests only; the default hasher is slow on purpose."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def make_user(db):
    """Return a factory that creates a user, optionally in a role group."""

    def _make_user(username: str, role: str | None = None, **fields) -> User:
        user = User.objects.create_user(username=username, password="pw", **fields)
        if role:
            user.groups.add(Group.objects.get(name=role))
        return user

    return _make_user


@pytest.fixture
def admin(make_user) -> User:
    return make_user("admin", first_name="Ada", last_name="Admin", is_superuser=True, is_staff=True)


@pytest.fixture
def recruiter(make_user) -> User:
    return make_user("recruiter", RECRUITER, first_name="Rae", last_name="Recruiter")


@pytest.fixture
def hiring_manager(make_user) -> User:
    return make_user("manager", HIRING_MANAGER, first_name="Hal", last_name="Manager")


@pytest.fixture
def interviewer(make_user) -> User:
    return make_user("interviewer", INTERVIEWER, first_name="Ivy", last_name="Interviewer")


@pytest.fixture
def no_role_user(make_user) -> User:
    return make_user("norole")
