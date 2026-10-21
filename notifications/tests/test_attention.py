"""The Needs attention panel and its navigation badge."""

import re
from html import unescape

import pytest
from django.urls import reverse

from accounts.roles import HIRING_MANAGER, RECRUITER
from applications.models import Application, StageChange
from applications.services import record_application
from applications.stages import Stage
from candidates.models import Candidate, Source
from notifications.attention import attention_count, closures_awaiting_decision
from openings.models import JobOpening, OpeningEvent
from openings.services import cancel_remaining_applications

pytestmark = pytest.mark.django_db

ATTENTION_URL = reverse("notifications:attention")


def page(response) -> str:
    return unescape(response.content.decode())


def text(response) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", page(response)).split())


@pytest.fixture
def riley(make_user):
    """A Recruiter who is the designated authority of one closed opening."""
    return make_user("riley", RECRUITER, first_name="Riley", last_name="Chen")


@pytest.fixture
def make_closed_with(make_opening, recruiter, hiring_manager):
    """Return a factory: an opening with one application per stage given, then closed."""
    indeed = Source.objects.create(name="Indeed", category=Source.Category.JOB_BOARD)

    def _make(title: str, authority, *stages: str, note: str = "") -> JobOpening:
        opening = make_opening(title, authority)
        for number, stage in enumerate(stages):
            candidate = Candidate.objects.create(
                first_name=f"C{number}",
                last_name=title,
                email=f"c{number}.{opening.pk}@example.com",
            )
            application = record_application(
                candidate=candidate, opening=opening, source=indeed, by=recruiter
            )
            if stage != Stage.APPLIED:
                StageChange.objects.create(
                    application=application,
                    from_stage=Stage.APPLIED,
                    to_stage=stage,
                    changed_by=recruiter,
                    note="Test setup.",
                )
                Application.objects.filter(pk=application.pk).update(stage=stage)
        JobOpening.objects.filter(pk=opening.pk).update(status=JobOpening.Status.CLOSED)
        OpeningEvent.objects.create(
            opening=opening, kind=OpeningEvent.Kind.CLOSED, by=recruiter, note=note
        )
        return JobOpening.objects.get(pk=opening.pk)

    return _make


@pytest.fixture
def closures(make_closed_with, make_opening, hiring_manager, riley, make_user):
    """Two closures awaiting a decision (Hal's and Riley's), and three that don't qualify."""
    other_manager = make_user("other", HIRING_MANAGER, first_name="Olive", last_name="Other")
    return {
        "hals": make_closed_with(
            "Backend Developer",
            hiring_manager,
            Stage.INTERVIEW,
            Stage.OFFER,
            Stage.HIRED,
            note="Budget moved.",
        ),
        "rileys": make_closed_with("Support Specialist", riley, Stage.APPLIED),
        # Only finished applications: nothing to decide.
        "finished": make_closed_with("QA Analyst", other_manager, Stage.HIRED, Stage.REJECTED),
        "empty": make_closed_with("UX Researcher", other_manager),
        # Open, with an active applicant: nothing to decide either.
        "open": make_opening("Data Engineer", other_manager),
    }


def titles(items) -> list[tuple[str, bool]]:
    return [(item.opening.title, item.assigned_to_you) for item in items]


@pytest.mark.parametrize(
    ("user_fixture", "expected"),
    [
        # Admins and Hiring Managers may decide for any opening; their own come first.
        ("admin", [("Backend Developer", False), ("Support Specialist", False)]),
        ("hiring_manager", [("Backend Developer", True), ("Support Specialist", False)]),
        # Riley may decide only for the opening they are the authority of.
        ("riley", [("Support Specialist", True)]),
        # A Recruiter who isn't an authority can close openings but decides nothing.
        ("recruiter", []),
        ("interviewer", []),
        ("no_role_user", []),
    ],
)
def test_the_panel_lists_only_the_closures_the_user_may_decide(
    request, closures, user_fixture, expected
):
    user = request.getfixturevalue(user_fixture)

    assert titles(closures_awaiting_decision(user)) == expected


def test_each_item_carries_its_active_count_and_closure(hiring_manager, closures):
    item = closures_awaiting_decision(hiring_manager)[0]

    assert item.opening.active_count == 2
    assert item.closed.note == "Budget moved."


def test_an_authority_who_is_no_longer_eligible_sees_nothing_assigned(riley, closures):
    riley.is_active = False
    riley.save()

    assert closures_awaiting_decision(riley) == []
    assert attention_count(riley) == 0


def test_an_opening_drops_off_once_its_applicants_are_cancelled(hiring_manager, closures):
    cancel_remaining_applications(closures["hals"], by=hiring_manager)

    assert titles(closures_awaiting_decision(hiring_manager)) == [("Support Specialist", False)]
    assert attention_count(hiring_manager) == 0


@pytest.mark.parametrize(
    ("user_fixture", "count"),
    [("hiring_manager", 1), ("riley", 1), ("admin", 0), ("recruiter", 0), ("interviewer", 0)],
)
def test_the_nav_badge_counts_only_closures_assigned_to_you(
    client, request, closures, user_fixture, count
):
    client.force_login(request.getfixturevalue(user_fixture))

    html = page(client.get(reverse("accounts:home")))

    assert 'data-testid="nav-attention"' in html
    badges = re.findall(r'data-testid="attention-count"[^>]*>(\d+)<', html)
    assert badges == ([str(count)] * 2 if count else [])  # the top bar and the sidebar


def test_the_page_groups_yours_and_others_and_links_to_each_opening(
    client, hiring_manager, closures
):
    client.force_login(hiring_manager)

    response = client.get(ATTENTION_URL)

    html, words = page(response), text(response)
    yours = html[
        html.index('data-testid="attention-yours"') : html.index('data-testid="attention-others"')
    ]
    assert "Backend Developer" in yours and "Support Specialist" not in yours
    assert "Support Specialist" in html[html.index('data-testid="attention-others"') :]
    assert "2 still in progress" in words
    assert '"Budget moved."' in words
    assert f'href="{closures["hals"].get_absolute_url()}#closure"' in html
    assert "QA Analyst" not in html and "UX Researcher" not in html and "Data Engineer" not in html


@pytest.mark.parametrize("user_fixture", ["recruiter", "interviewer"])
def test_users_with_nothing_to_decide_see_an_empty_panel(client, request, closures, user_fixture):
    client.force_login(request.getfixturevalue(user_fixture))

    response = client.get(ATTENTION_URL)

    assert response.status_code == 200
    assert 'data-testid="attention-empty"' in page(response)


def test_anonymous_users_are_sent_to_log_in(client):
    response = client.get(ATTENTION_URL)

    assert response.status_code == 302
    assert response.url.startswith(reverse("accounts:login"))
