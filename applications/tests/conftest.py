"""Fixtures for the applications tests: candidates, sources and openings to apply for."""

import pytest

from applications.models import Application
from applications.services import record_application
from candidates.models import Candidate, Source
from openings.models import JobOpening


@pytest.fixture
def ann(db) -> Candidate:
    return Candidate.objects.create(first_name="Ann", last_name="Lee", email="ann@example.com")


@pytest.fixture
def ben(db) -> Candidate:
    return Candidate.objects.create(first_name="Ben", last_name="Ortiz", email="ben@example.com")


@pytest.fixture
def indeed(db) -> Source:
    return Source.objects.create(name="Indeed", category=Source.Category.JOB_BOARD)


@pytest.fixture
def linkedin(db) -> Source:
    return Source.objects.create(name="LinkedIn Jobs", category=Source.Category.JOB_BOARD)


@pytest.fixture
def referral(db) -> Source:
    return Source.objects.create(name="Employee referral", category=Source.Category.REFERRAL)


@pytest.fixture
def monster(db) -> Source:
    """A retired source: old applications keep it, new ones can't pick it."""
    return Source.objects.create(
        name="Monster", category=Source.Category.JOB_BOARD, is_active=False
    )


@pytest.fixture
def backend(make_opening, hiring_manager) -> JobOpening:
    return make_opening("Backend Developer", hiring_manager)


@pytest.fixture
def qa(make_opening, hiring_manager) -> JobOpening:
    return make_opening("QA Analyst", hiring_manager)


@pytest.fixture
def closed_opening(make_opening, hiring_manager) -> JobOpening:
    return make_opening(
        "UX Researcher", hiring_manager, department="Design", status=JobOpening.Status.CLOSED
    )


@pytest.fixture
def apply(recruiter):
    """Return a shortcut that records an application through the service, as the Recruiter."""

    def _apply(candidate, opening, source, **fields) -> Application:
        return record_application(
            candidate=candidate, opening=opening, source=source, by=recruiter, **fields
        )

    return _apply


@pytest.fixture
def app(apply, ann, backend, indeed) -> Application:
    """Ann's application for Backend Developer, whose authority is Hal (a Hiring Manager)."""
    return apply(ann, backend, indeed)
