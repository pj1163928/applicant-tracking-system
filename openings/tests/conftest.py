"""Fixtures for the openings tests."""

import pytest

from accounts.roles import HIRING_MANAGER


@pytest.fixture
def inactive_manager(make_user):
    """A Hiring Manager who has left: never an eligible authority."""
    return make_user(
        "gone-manager", HIRING_MANAGER, first_name="Gil", last_name="Gone", is_active=False
    )
