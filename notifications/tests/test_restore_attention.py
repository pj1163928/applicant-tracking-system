"""Reopened openings waiting for a restore choice, in Needs attention and its navigation badge."""

import re
from html import unescape

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.roles import RECRUITER
from applications.services import record_application
from applications.stages import Stage
from candidates.models import Candidate, Source
from notifications.attention import (
    AttentionSummary,
    attention_count,
    attention_summary,
    restores_awaiting_choice,
)
from openings.models import JobOpening
from openings.services import reopen_opening, restore_applications
from openings.tests.conftest import cancel_directly, close_directly, move_directly, reopen_directly

pytestmark = pytest.mark.django_db

ATTENTION_URL = reverse("notifications:attention")


def text(response) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", unescape(response.content.decode())).split())


@pytest.fixture
def riley(make_user):
    return make_user("riley", RECRUITER, first_name="Riley", last_name="Chen")


@pytest.fixture
def make_cancelled(make_opening, recruiter):
    """Return a factory: an opening with one application per stage given, closed and cancelled."""
    indeed = Source.objects.create(name="Indeed", category=Source.Category.JOB_BOARD)

    def _make(title: str, authority, *stages: str) -> JobOpening:
        opening = make_opening(title, authority)
        applications = []
        for number, stage in enumerate(stages):
            candidate = Candidate.objects.create(
                first_name=f"C{number}", last_name=title, email=f"c{number}.{opening.pk}@x.com"
            )
            application = record_application(
                candidate=candidate, opening=opening, source=indeed, by=recruiter
            )
            if stage != Stage.APPLIED:
                move_directly(application, stage, recruiter)
            applications.append(application)
        closure = close_directly(opening, recruiter)
        for application in applications:
            cancel_directly(application, closure, recruiter)
        return opening

    return _make


def titles(items) -> list[tuple[str, bool]]:
    return [(item.opening.title, item.assigned_to_you) for item in items]


def test_a_recruiters_reopen_puts_the_restore_choice_in_the_authoritys_panel(
    client, make_cancelled, recruiter, hiring_manager
):
    opening = make_cancelled("Backend Developer", hiring_manager, Stage.SCREENING, Stage.OFFER)
    assert restores_awaiting_choice(hiring_manager) == []

    reopen_opening(opening, by=recruiter)

    items = restores_awaiting_choice(hiring_manager)
    assert titles(items) == [("Backend Developer", True)]
    assert items[0].opening.restorable_count == 2
    assert items[0].reopened.by == recruiter
    assert attention_count(hiring_manager) == 1
    client.force_login(hiring_manager)
    response = client.get(ATTENTION_URL)
    assert "2 applicants cancelled when it closed are waiting" in text(response)
    assert reverse("openings:restore", args=[opening.pk]) in response.content.decode()


@pytest.mark.parametrize(
    ("user_fixture", "expected"),
    [
        ("admin", [("Backend Developer", False), ("Support Specialist", False)]),
        ("hiring_manager", [("Backend Developer", True), ("Support Specialist", False)]),
        ("riley", [("Support Specialist", True)]),
        ("recruiter", []),
        ("interviewer", []),
    ],
)
def test_restore_choices_go_to_those_who_may_decide_theirs_first(
    request, make_cancelled, recruiter, hiring_manager, riley, user_fixture, expected
):
    for opening in (
        make_cancelled("Backend Developer", hiring_manager, Stage.INTERVIEW),
        make_cancelled("Support Specialist", riley, Stage.APPLIED),
    ):
        reopen_directly(opening, recruiter)

    assert titles(restores_awaiting_choice(request.getfixturevalue(user_fixture))) == expected


def test_the_summary_counts_restore_choices_as_the_panel_groups_them(
    make_cancelled, recruiter, hiring_manager, riley
):
    for opening in (
        make_cancelled("Backend Developer", hiring_manager, Stage.INTERVIEW),
        make_cancelled("Support Specialist", riley, Stage.APPLIED),
    ):
        reopen_directly(opening, recruiter)

    assert attention_summary(hiring_manager) == AttentionSummary(1, 1, True)
    assert attention_summary(riley) == AttentionSummary(1, 0, False)


def test_making_the_choice_takes_it_out_of_the_panel(make_cancelled, recruiter, hiring_manager):
    opening = make_cancelled("Backend Developer", hiring_manager, Stage.SCREENING, Stage.APPLIED)
    reopen_directly(opening, recruiter)
    first = opening.applications.order_by("pk").first()

    restore_applications(opening, [first], by=hiring_manager)

    # One is left cancelled, but the choice was made, so it waits on nobody.
    assert restores_awaiting_choice(hiring_manager) == []
    assert attention_count(hiring_manager) == 0


def test_choosing_nobody_takes_it_out_of_the_panel_too(make_cancelled, recruiter, hiring_manager):
    opening = make_cancelled("Backend Developer", hiring_manager, Stage.SCREENING)
    reopen_directly(opening, recruiter)

    restore_applications(opening, [], by=hiring_manager)

    assert restores_awaiting_choice(hiring_manager) == []


def test_a_reopening_with_nobody_left_to_restore_needs_no_choice(
    make_cancelled, recruiter, hiring_manager
):
    opening = make_cancelled("Backend Developer", hiring_manager, Stage.SCREENING)
    reopen_directly(opening, recruiter)
    move_directly(opening.applications.get(), Stage.SCREENING, hiring_manager)  # moved by hand

    assert restores_awaiting_choice(hiring_manager) == []


def test_archived_applicants_still_count_as_waiting(make_cancelled, recruiter, hiring_manager):
    opening = make_cancelled("Backend Developer", hiring_manager, Stage.SCREENING)
    Candidate.objects.update(is_archived=True, archived_at=timezone.now())
    reopen_directly(opening, recruiter)

    assert titles(restores_awaiting_choice(hiring_manager)) == [("Backend Developer", True)]


def test_closing_again_before_the_choice_takes_it_out_of_the_panel(
    make_cancelled, recruiter, hiring_manager
):
    opening = make_cancelled("Backend Developer", hiring_manager, Stage.SCREENING)
    reopen_directly(opening, recruiter)

    close_directly(opening, recruiter)

    assert restores_awaiting_choice(hiring_manager) == []


def test_the_choice_returns_after_a_later_reopening(make_cancelled, recruiter, hiring_manager):
    opening = make_cancelled("Backend Developer", hiring_manager, Stage.SCREENING)
    reopen_directly(opening, recruiter)
    restore_applications(opening, opening.applications.all(), by=hiring_manager)
    closure = close_directly(opening, recruiter)
    cancel_directly(opening.applications.get(), closure, recruiter)

    reopen_directly(opening, recruiter)

    assert titles(restores_awaiting_choice(hiring_manager)) == [("Backend Developer", True)]
