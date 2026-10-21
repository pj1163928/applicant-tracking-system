"""Fixtures for the notifications tests: one recorded application to write to."""

import pytest

from applications.models import Application
from applications.services import record_application
from candidates.models import Candidate, Source


@pytest.fixture
def application(make_opening, hiring_manager, recruiter) -> Application:
    """Ann Lee's application for Backend Developer, at Applied."""
    ann = Candidate.objects.create(first_name="Ann", last_name="Lee", email="ann@example.com")
    indeed = Source.objects.create(name="Indeed", category=Source.Category.JOB_BOARD)
    backend = make_opening("Backend Developer", hiring_manager)
    return record_application(candidate=ann, opening=backend, source=indeed, by=recruiter)
