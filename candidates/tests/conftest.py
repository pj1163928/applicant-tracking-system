"""Fixtures for the candidates tests that need applications: an opening, a source, a helper."""

import pytest

from applications.models import Application, StageChange
from applications.services import record_application
from candidates.models import Candidate, Source
from openings.models import JobOpening


@pytest.fixture
def kai(db) -> Candidate:
    return Candidate.objects.create(first_name="Kai", last_name="Moreno", email="kai@example.com")


@pytest.fixture
def indeed(db) -> Source:
    return Source.objects.create(name="Indeed", category=Source.Category.JOB_BOARD)


@pytest.fixture
def backend(make_opening, hiring_manager) -> JobOpening:
    return make_opening("Backend Developer", hiring_manager)


@pytest.fixture
def qa(make_opening, hiring_manager) -> JobOpening:
    return make_opening("QA Analyst", hiring_manager)


@pytest.fixture
def application_at(recruiter, indeed):
    """Return a helper that records ``candidate``'s application for ``opening`` at ``stage``.

    The application is recorded through the service, then put at its stage
    with direct writes, so the setup doesn't depend on ``move_application``.
    """

    def _application_at(candidate, opening, stage) -> Application:
        application = record_application(
            candidate=candidate, opening=opening, source=indeed, by=recruiter
        )
        if stage != application.stage:
            StageChange.objects.create(
                application=application,
                from_stage=application.stage,
                to_stage=stage,
                changed_by=recruiter,
                note="Test setup.",
            )
            Application.objects.filter(pk=application.pk).update(stage=stage)
            application.stage = stage
        return application

    return _application_at
