"""Fixtures for the openings tests."""

import pytest

from accounts.roles import HIRING_MANAGER
from openings.models import JobOpening


@pytest.fixture
def make_opening(db):
    """Return a factory that creates an opening with sensible defaults."""

    def _make_opening(title: str, authority, **fields) -> JobOpening:
        fields.setdefault("department", "Engineering")
        fields.setdefault("description", f"About the {title} role.")
        return JobOpening.objects.create(title=title, designated_authority=authority, **fields)

    return _make_opening


@pytest.fixture
def inactive_manager(make_user):
    """A Hiring Manager who has left: never an eligible authority."""
    return make_user(
        "gone-manager", HIRING_MANAGER, first_name="Gil", last_name="Gone", is_active=False
    )
