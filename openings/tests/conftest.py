"""Fixtures for the openings tests."""

import pytest

from accounts.roles import HIRING_MANAGER, RECRUITER
from applications.models import Application, StageChange
from applications.services import record_application
from candidates.models import Candidate, Source
from openings.models import JobOpening, OpeningEvent


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


@pytest.fixture
def indeed(db):
    return Source.objects.create(name="Indeed", category=Source.Category.JOB_BOARD)


@pytest.fixture
def backend(make_opening, hiring_manager):
    """An opening whose designated authority is Hal, a Hiring Manager."""
    return make_opening("Backend Developer", hiring_manager)


@pytest.fixture
def make_candidate(db):
    """Return a factory for a candidate called ``first_name`` Test."""

    def _make_candidate(first_name: str) -> Candidate:
        return Candidate.objects.create(
            first_name=first_name, last_name="Test", email=f"{first_name.lower()}@example.com"
        )

    return _make_candidate


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


def close_directly(opening, by) -> OpeningEvent:
    """Close ``opening`` with direct writes, as ``close_opening`` would, without calling it."""
    JobOpening.objects.filter(pk=opening.pk).update(status=JobOpening.Status.CLOSED)
    opening.status = JobOpening.Status.CLOSED
    return OpeningEvent.objects.create(opening=opening, kind=OpeningEvent.Kind.CLOSED, by=by)
