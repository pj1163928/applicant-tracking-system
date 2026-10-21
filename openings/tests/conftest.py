"""Fixtures for the openings tests."""

import pytest

from accounts.roles import HIRING_MANAGER, RECRUITER


@pytest.fixture
def inactive_manager(make_user):
    """A Hiring Manager who has left: never an eligible authority."""
    return make_user(
        "gone-manager", HIRING_MANAGER, first_name="Gil", last_name="Gone", is_active=False
    )


@pytest.fixture
def authority(make_user):
    """A Recruiter who is ``skilled_opening``'s designated authority, and no other's."""
    return make_user("riley", RECRUITER, first_name="Riley", last_name="Chen")


@pytest.fixture
def skilled_opening(make_opening, authority):
    """An opening whose designated authority is a Recruiter, so Recruiters split on it."""
    return make_opening("Support Specialist", authority, department="Operations")
