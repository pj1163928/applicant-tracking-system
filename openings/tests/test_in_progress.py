"""The Admin in-progress view: closed openings whose applicants are still in progress."""

import re
from datetime import date, timedelta
from html import unescape

import pytest
from django.urls import reverse
from django.utils import timezone

from applications.models import Application
from applications.stages import Stage
from openings.grace import ClosureStatus
from openings.in_progress import InProgressCounts, in_progress_counts, in_progress_openings
from openings.models import JobOpening
from openings.services import cancel_remaining_applications
from openings.tests.conftest import close_directly, grace_directly

pytestmark = pytest.mark.django_db

IN_PROGRESS_URL = reverse("in_progress:list")
TODAY = date(2026, 11, 9)
FLAG = JobOpening.GraceExpiryAction.FLAG_OVERDUE
AUTO = JobOpening.GraceExpiryAction.AUTO_CANCEL


def page(response) -> str:
    return unescape(response.content.decode())


def text(response) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", page(response)).split())


@pytest.fixture
def make_closed(make_opening, make_candidate, application_at, hiring_manager, recruiter):
    """Return a factory: an opening with one application per stage given, closed unless told not."""
    made = []

    def _make(title: str, *stages: str, authority=None, close: bool = True) -> JobOpening:
        opening = make_opening(title, authority or hiring_manager)
        for stage in stages:
            application_at(make_candidate(f"{title.split()[0]}{len(made)}"), opening, stage)
            made.append(stage)
        if close:
            close_directly(opening, recruiter)
        return opening

    return _make


def expire_directly(opening, on: date) -> None:
    """Mark ``opening``'s grace period as ended by the daily run on ``on``, with a direct write."""
    JobOpening.objects.filter(pk=opening.pk).update(grace_expired_on=on)


def titles(items) -> list[str]:
    return [item.opening.title for item in items]


# The listing


def test_only_closed_openings_with_an_active_application_are_listed(make_closed):
    make_closed("Open Role", Stage.INTERVIEW, close=False)
    make_closed("Nobody Applied")
    make_closed("All Decided", Stage.HIRED, Stage.REJECTED, Stage.WITHDRAWN)
    listed = make_closed("Still Going", Stage.SCREENING, Stage.REJECTED, Stage.OFFER)

    items = in_progress_openings(today=TODAY)

    assert titles(items) == ["Still Going"]
    assert items[0].opening.pk == listed.pk
    assert items[0].opening.active_count == 2


def test_each_opening_gets_its_status_on_the_day_given_most_urgent_first(make_closed, recruiter):
    awaiting = make_closed("Awaiting Role", Stage.APPLIED)
    in_grace = make_closed("Grace Role", Stage.APPLIED)
    grace_directly(
        in_grace, by=recruiter, ends=TODAY + timedelta(days=3), set_on=TODAY, action=FLAG
    )
    overdue = make_closed("Overdue Role", Stage.APPLIED)
    grace_directly(overdue, by=recruiter, ends=TODAY, set_on=TODAY - timedelta(days=4), action=FLAG)
    late_cancel = make_closed("Late Cancel Role", Stage.APPLIED)
    grace_directly(
        late_cancel, by=recruiter, ends=TODAY, set_on=TODAY - timedelta(days=4), action=AUTO
    )
    cancelled_then_back = make_closed("Back Again Role", Stage.APPLIED)
    grace_directly(
        cancelled_then_back,
        by=recruiter,
        ends=TODAY - timedelta(days=2),
        set_on=TODAY - timedelta(days=6),
        action=AUTO,
    )
    expire_directly(cancelled_then_back, on=TODAY - timedelta(days=2))

    items = in_progress_openings(today=TODAY)

    assert [(item.opening.title, item.status, item.days_left) for item in items] == [
        ("Late Cancel Role", ClosureStatus.OVERDUE, None),
        ("Overdue Role", ClosureStatus.OVERDUE, None),
        ("Awaiting Role", ClosureStatus.AWAITING_DECISION, None),
        ("Back Again Role", ClosureStatus.AWAITING_DECISION, None),
        ("Grace Role", ClosureStatus.IN_GRACE_PERIOD, 3),
    ]
    assert {item.opening.pk for item in items} == {
        awaiting.pk,
        in_grace.pk,
        overdue.pk,
        late_cancel.pk,
        cancelled_then_back.pk,
    }


def test_a_grace_period_is_in_progress_the_day_before_its_end_and_overdue_on_it(
    make_closed, recruiter
):
    opening = make_closed("Data Engineer", Stage.APPLIED)
    grace_directly(opening, by=recruiter, ends=TODAY, set_on=TODAY - timedelta(days=4), action=FLAG)

    (before,) = in_progress_openings(today=TODAY - timedelta(days=1))
    (on_the_day,) = in_progress_openings(today=TODAY)

    assert (before.status, before.days_left) == (ClosureStatus.IN_GRACE_PERIOD, 1)
    assert (on_the_day.status, on_the_day.days_left) == (ClosureStatus.OVERDUE, None)


def test_each_item_carries_the_latest_closure(make_closed, recruiter):
    opening = make_closed("QA Analyst", Stage.APPLIED)
    latest = close_directly(opening, recruiter)

    (item,) = in_progress_openings(today=TODAY)

    assert item.closed == latest


def test_an_opening_drops_off_once_nobody_is_in_progress(make_closed, hiring_manager):
    opening = make_closed("UX Researcher", Stage.APPLIED, Stage.INTERVIEW)
    assert titles(in_progress_openings(today=TODAY)) == ["UX Researcher"]

    cancel_remaining_applications(opening, by=hiring_manager)

    assert in_progress_openings(today=TODAY) == []


def test_an_opening_drops_off_once_its_last_applicant_is_hired(make_closed):
    opening = make_closed("Support Specialist", Stage.OFFER)

    Application.objects.filter(opening=opening).update(stage=Stage.HIRED)

    assert in_progress_openings(today=TODAY) == []


def test_today_defaults_to_the_project_time_zone_date(make_closed, recruiter):
    opening = make_closed("Data Engineer", Stage.APPLIED)
    today = timezone.localdate()
    grace_directly(opening, by=recruiter, ends=today, set_on=today - timedelta(days=4), action=FLAG)

    (item,) = in_progress_openings()

    assert item.status == ClosureStatus.OVERDUE


# The page


def test_anonymous_users_are_sent_to_log_in(client):
    response = client.get(IN_PROGRESS_URL)

    assert response.status_code == 302
    assert response.url.startswith(reverse("accounts:login"))


@pytest.mark.parametrize(
    "user_fixture", ["recruiter", "hiring_manager", "interviewer", "no_role_user"]
)
def test_only_admins_can_open_the_page(client, request, user_fixture):
    client.force_login(request.getfixturevalue(user_fixture))

    assert client.get(IN_PROGRESS_URL).status_code == 403


def test_admins_see_each_opening_with_its_authority_count_status_and_link(
    client, admin, make_closed, recruiter, hiring_manager
):
    today = timezone.localdate()
    awaiting = make_closed("QA Analyst", Stage.APPLIED, Stage.SCREENING, authority=recruiter)
    in_grace = make_closed("Data Engineer", Stage.APPLIED)
    grace_directly(
        in_grace, by=recruiter, ends=today + timedelta(days=2), set_on=today, action=AUTO
    )
    overdue = make_closed("UX Researcher", Stage.INTERVIEW)
    grace_directly(overdue, by=recruiter, ends=today, set_on=today - timedelta(days=4), action=FLAG)
    make_closed("Open Role", Stage.APPLIED, close=False)
    client.force_login(admin)

    response = client.get(IN_PROGRESS_URL)
    html = page(response)

    assert response.status_code == 200
    statuses = re.findall(r'data-testid="in-progress-item" data-status="(\w+)"', html)
    assert statuses == ["overdue", "awaiting_decision", "in_grace_period"]
    for opening in (awaiting, in_grace, overdue):
        assert f'href="{opening.get_absolute_url()}#closure"' in html
    assert "Open Role" not in html
    words = text(response)
    assert "UX Researcher Overdue 1 still in progress" in words
    assert "QA Analyst Awaiting decision 2 still in progress" in words
    assert "Data Engineer In grace period 1 still in progress" in words
    assert "2 days left, then the remaining applications are cancelled." in words
    assert "Rae Recruiter" in words and "Hal Manager" in words
    counts = re.findall(
        r'data-testid="in-progress-count" data-status="(\w+)">.*?(\d+)</span>', html, re.S
    )
    assert counts == [("overdue", "1"), ("awaiting_decision", "1"), ("in_grace_period", "1")]


def test_an_auto_cancel_the_daily_run_missed_is_flagged_on_the_page(
    client, admin, make_closed, recruiter
):
    today = timezone.localdate()
    opening = make_closed("Data Engineer", Stage.APPLIED)
    grace_directly(opening, by=recruiter, ends=today, set_on=today - timedelta(days=4), action=AUTO)
    client.force_login(admin)

    words = text(client.get(IN_PROGRESS_URL))

    assert "Data Engineer Overdue" in words
    assert "the remaining applications haven't been cancelled yet" in words


def test_the_page_says_so_when_nothing_is_in_progress(client, admin, make_closed):
    make_closed("All Decided", Stage.HIRED)
    client.force_login(admin)

    response = client.get(IN_PROGRESS_URL)

    assert 'data-testid="in-progress-empty"' in page(response)
    assert 'data-testid="in-progress-item"' not in page(response)


@pytest.mark.parametrize(
    ("user_fixture", "shown"),
    [
        ("admin", True),
        ("recruiter", False),
        ("hiring_manager", False),
        ("interviewer", False),
        ("no_role_user", False),
    ],
)
def test_only_admins_see_the_navigation_link(client, request, user_fixture, shown):
    client.force_login(request.getfixturevalue(user_fixture))

    html = page(client.get(reverse("accounts:home")))

    assert ('data-testid="nav-in-progress"' in html) is shown
    assert (f'href="{IN_PROGRESS_URL}"' in html) is shown


# The navigation's counts


def test_the_counts_match_the_listing_and_leave_grace_periods_out_of_to_act_on(
    make_closed, recruiter
):
    make_closed("Awaiting Role", Stage.APPLIED)
    make_closed("Second Awaiting Role", Stage.SCREENING, Stage.INTERVIEW)
    overdue = make_closed("Overdue Role", Stage.APPLIED)
    grace_directly(overdue, by=recruiter, ends=TODAY, set_on=TODAY - timedelta(days=4), action=FLAG)
    in_grace = make_closed("Grace Role", Stage.APPLIED)
    grace_directly(
        in_grace, by=recruiter, ends=TODAY + timedelta(days=3), set_on=TODAY, action=AUTO
    )
    make_closed("All Decided", Stage.HIRED)
    make_closed("Open Role", Stage.APPLIED, close=False)

    counts = in_progress_counts(today=TODAY)

    assert counts == InProgressCounts(overdue=1, awaiting_decision=2, in_grace_period=1)
    assert (counts.to_act_on, counts.total) == (3, 4)
    statuses = [item.status for item in in_progress_openings(today=TODAY)]
    assert counts.total == len(statuses)
    assert counts.overdue == statuses.count(ClosureStatus.OVERDUE)


def nav(client) -> str:
    return page(client.get(reverse("accounts:home")))


def test_the_admin_nav_badge_counts_what_needs_action_and_turns_red_when_overdue(
    client, admin, make_closed, recruiter
):
    today = timezone.localdate()
    make_closed("QA Analyst", Stage.APPLIED)
    overdue = make_closed("UX Researcher", Stage.APPLIED)
    grace_directly(overdue, by=recruiter, ends=today, set_on=today - timedelta(days=4), action=FLAG)
    in_grace = make_closed("Data Engineer", Stage.APPLIED)
    grace_directly(
        in_grace, by=recruiter, ends=today + timedelta(days=2), set_on=today, action=FLAG
    )
    client.force_login(admin)

    html = nav(client)

    badges = re.findall(
        r'class="badge badge-sm (badge-\w+)" data-testid="nav-in-progress-count"[^>]*>(\d+)<', html
    )
    assert badges == [("badge-error", "2")] * 2  # the top bar and the sidebar
    assert 'aria-label="2 need action, 1 overdue"' in html
    lines = re.findall(r'data-testid="in-progress-breakdown-line">([^<]*)<', html)
    assert lines == ["1 overdue · 1 awaiting · 1 in grace"] * 2
    popup = html[html.index('data-testid="in-progress-breakdown"') :]
    popup = " ".join(re.sub(r"<[^>]+>", " ", popup[: popup.index('class="nav-breakdown"')]).split())
    assert "In progress Overdue 1 Awaiting decision 1 In grace period (not counted) 1" in popup


def test_the_admin_nav_badge_is_amber_without_anything_overdue(client, admin, make_closed):
    make_closed("QA Analyst", Stage.APPLIED)
    client.force_login(admin)

    badges = re.findall(
        r'class="badge badge-sm (badge-\w+)" data-testid="nav-in-progress-count"[^>]*>(\d+)<',
        nav(client),
    )

    assert badges == [("badge-warning", "1")] * 2


def test_a_grace_period_alone_gets_a_breakdown_but_no_badge(client, admin, make_closed, recruiter):
    today = timezone.localdate()
    in_grace = make_closed("Data Engineer", Stage.APPLIED)
    grace_directly(
        in_grace, by=recruiter, ends=today + timedelta(days=2), set_on=today, action=FLAG
    )
    client.force_login(admin)

    html = nav(client)

    assert 'data-testid="nav-in-progress-count"' not in html
    assert html.count('data-testid="in-progress-breakdown"') == 2


def test_the_admin_nav_shows_no_count_or_breakdown_when_nothing_is_in_progress(
    client, admin, make_closed
):
    make_closed("All Decided", Stage.HIRED)
    client.force_login(admin)

    html = nav(client)

    assert 'data-testid="nav-in-progress"' in html
    assert 'data-testid="nav-in-progress-count"' not in html
    assert 'data-testid="in-progress-breakdown"' not in html
