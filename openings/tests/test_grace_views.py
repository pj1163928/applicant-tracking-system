"""Setting and extending a grace period through the pages, and the closure panel's states."""

import re
from datetime import date, timedelta
from html import unescape

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from applications.models import StageChange
from applications.stages import Stage
from notifications.models import CandidateMessage
from openings.models import JobOpening, OpeningEvent
from openings.tests.conftest import close_directly, grace_directly

pytestmark = pytest.mark.django_db

FLAG_OVERDUE = JobOpening.GraceExpiryAction.FLAG_OVERDUE
AUTO_CANCEL = JobOpening.GraceExpiryAction.AUTO_CANCEL


def page(response) -> str:
    return unescape(response.content.decode())


def text(response) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", page(response)).split())


def latest_message(response) -> str:
    return [str(m) for m in get_messages(response.wsgi_request)][-1]


def set_url(opening) -> str:
    return reverse("openings:grace_period", args=[opening.pk])


def extend_url(opening) -> str:
    return reverse("openings:extend_grace_period", args=[opening.pk])


def detail(client, opening):
    return client.get(reverse("openings:detail", args=[opening.pk]))


def snapshot(opening):
    stored = JobOpening.objects.get(pk=opening.pk)
    return (
        stored.grace_period_ends,
        stored.grace_expiry_action,
        stored.grace_period_set_on,
        stored.grace_expired_on,
        StageChange.objects.count(),
        OpeningEvent.objects.count(),
        CandidateMessage.objects.count(),
    )


def today() -> date:
    return timezone.localdate()


@pytest.fixture
def awaiting(backend, hiring_manager, make_candidate, application_at):
    """Backend Developer, closed with Ann at Interview and Ben hired: a decision awaits Hal."""
    application_at(make_candidate("Ann"), backend, Stage.INTERVIEW)
    application_at(make_candidate("Ben"), backend, Stage.HIRED)
    close_directly(backend, hiring_manager)
    return backend


@pytest.fixture
def in_grace(awaiting, hiring_manager):
    """``awaiting``, in a flag-overdue grace period that ends in 5 days."""
    grace_directly(
        awaiting,
        by=hiring_manager,
        ends=today() + timedelta(days=5),
        set_on=today() - timedelta(days=2),
        action=FLAG_OVERDUE,
    )
    return awaiting


def overdue(opening) -> JobOpening:
    """Mark ``opening``'s grace period as ended yesterday, as the daily run would."""
    JobOpening.objects.filter(pk=opening.pk).update(
        grace_period_ends=today() - timedelta(days=1), grace_expired_on=today() - timedelta(days=1)
    )
    return JobOpening.objects.get(pk=opening.pk)


# Who may use the pages


@pytest.mark.parametrize("user_fixture", ["recruiter", "interviewer", "no_role_user"])
@pytest.mark.parametrize("url", [set_url, extend_url])
def test_those_who_cant_decide_get_403_for_get_and_post_and_nothing_changes(
    client, request, in_grace, user_fixture, url
):
    client.force_login(request.getfixturevalue(user_fixture))
    before = snapshot(in_grace)

    statuses = (
        client.get(url(in_grace)).status_code,
        client.post(
            url(in_grace),
            {"days": 7, "action": FLAG_OVERDUE, "ends": "2099-01-01", "note": "x"},
        ).status_code,
    )

    assert statuses == (403, 403)
    assert snapshot(in_grace) == before


@pytest.mark.parametrize("url", [set_url, extend_url])
def test_anonymous_users_are_sent_to_log_in(client, awaiting, url):
    response = client.get(url(awaiting))

    assert response.status_code == 302
    assert response.url.startswith(reverse("accounts:login"))


# Setting


def test_the_set_page_lists_who_will_be_emailed_and_both_actions(client, hiring_manager, awaiting):
    client.force_login(hiring_manager)

    response = client.get(set_url(awaiting))

    words = text(response)
    assert response.status_code == 200
    assert "Give 1 applicant a grace period?" in words
    assert "Ann Test" in words and "Ben Test" not in words
    assert "Cancel the remaining applications" in words
    assert "Flag the opening as overdue" in words
    assert "Candidates are told their application will be closed." in words
    assert "Candidates are told their application may be closed." in words


def test_setting_through_the_page_stores_it_emails_and_says_so(
    client, hiring_manager, awaiting, django_capture_on_commit_callbacks, mailoutbox
):
    client.force_login(hiring_manager)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(set_url(awaiting), {"days": "7", "action": AUTO_CANCEL})

    assert response.status_code == 302
    assert response.url == awaiting.get_absolute_url()
    stored = JobOpening.objects.get(pk=awaiting.pk)
    ends = today() + timedelta(days=7)
    assert (stored.grace_period_ends, stored.grace_expiry_action) == (ends, AUTO_CANCEL)
    assert [m.to[0] for m in mailoutbox] == ["ann@example.com"]
    assert latest_message(response) == (
        f"Gave the applicants for Backend Developer a grace period of 7 days, ending "
        f"{ends:%b} {ends.day}, {ends.year}. The applicant has been emailed."
    )


def test_a_recruiter_who_is_the_authority_can_set_one_through_the_page(
    client, skilled_opening, authority, make_candidate, application_at
):
    application_at(make_candidate("Ann"), skilled_opening, Stage.SCREENING)
    close_directly(skilled_opening, authority)
    client.force_login(authority)

    response = client.post(set_url(skilled_opening), {"days": "3", "action": FLAG_OVERDUE})

    assert response.status_code == 302
    assert JobOpening.objects.get(pk=skilled_opening.pk).has_grace_period


@pytest.mark.parametrize(
    ("data", "error"),
    [
        ({"days": "0", "action": FLAG_OVERDUE}, ("days", "at least 1 day")),
        ({"days": "91", "action": FLAG_OVERDUE}, ("days", "at most 90 days")),
        ({"days": "", "action": FLAG_OVERDUE}, ("days", "Say how many days")),
        ({"days": "7"}, ("action", "Choose what happens when the grace period ends.")),
        ({"days": "7", "action": "delete_everyone"}, ("action", "Select a valid choice")),
    ],
)
def test_the_set_form_shows_errors_and_nothing_changes(
    client, hiring_manager, awaiting, data, error
):
    client.force_login(hiring_manager)
    before = snapshot(awaiting)

    response = client.post(set_url(awaiting), data)

    field, words = error
    assert response.status_code == 200
    assert f'data-testid="error-{field}"' in page(response)
    assert words in text(response)
    assert snapshot(awaiting) == before


def test_the_set_page_sends_you_back_when_a_grace_period_exists(client, hiring_manager, in_grace):
    client.force_login(hiring_manager)
    before = snapshot(in_grace)

    responses = [
        client.get(set_url(in_grace)),
        client.post(set_url(in_grace), {"days": "3", "action": AUTO_CANCEL}),
    ]

    for response in responses:
        assert response.status_code == 302
        assert latest_message(response) == (
            "Backend Developer already has a grace period. Extend it instead."
        )
    assert snapshot(in_grace) == before


def test_the_set_page_sends_you_back_from_an_open_opening(client, hiring_manager, backend):
    client.force_login(hiring_manager)

    response = client.get(set_url(backend))

    assert response.status_code == 302
    assert latest_message(response) == (
        "Backend Developer is open, so its applicants need no grace period."
    )


# Extending


def test_the_extend_page_offers_the_allowed_dates(client, hiring_manager, in_grace):
    client.force_login(hiring_manager)

    response = client.get(extend_url(in_grace))

    html, words = page(response), text(response)
    earliest = in_grace.grace_period_ends + timedelta(days=1)
    latest = today() + timedelta(days=90)
    assert response.status_code == 200
    assert f'min="{earliest.isoformat()}"' in html
    assert f'max="{latest.isoformat()}"' in html
    assert "their 3-day and 1-day reminders follow the new date" in words


def test_extending_through_the_page_moves_the_date_and_says_so(client, hiring_manager, in_grace):
    client.force_login(hiring_manager)
    ends = today() + timedelta(days=12)

    response = client.post(
        extend_url(in_grace), {"ends": ends.isoformat(), "note": "Final round moved."}
    )

    assert response.status_code == 302
    assert JobOpening.objects.get(pk=in_grace.pk).grace_period_ends == ends
    assert latest_message(response) == (
        f"Extended the grace period for Backend Developer to {ends:%b} {ends.day}, "
        f"{ends.year}. Reminders will follow the new date."
    )
    event = in_grace.events.get(kind=OpeningEvent.Kind.GRACE_PERIOD_EXTENDED)
    assert event.note.endswith("Reason: Final round moved.")


@pytest.mark.parametrize(
    ("data", "field", "words"),
    [
        ({"ends": "2099-01-01"}, "note", "Say why the grace period is being extended."),
        ({"ends": "", "note": "Why."}, "ends", "Pick the new end date."),
        ({"ends": "not a date", "note": "Why."}, "ends", "Pick the new end date."),
        ({"ends": "2099-01-01", "note": "Why."}, "ends", "Pick an end date from"),
    ],
)
def test_the_extend_form_shows_errors_and_nothing_changes(
    client, hiring_manager, in_grace, data, field, words
):
    client.force_login(hiring_manager)
    before = snapshot(in_grace)

    response = client.post(extend_url(in_grace), data)

    assert response.status_code == 200
    assert f'data-testid="error-{field}"' in page(response)
    assert words in text(response)
    assert snapshot(in_grace) == before


def test_the_extend_form_refuses_the_current_end_date(client, hiring_manager, in_grace):
    client.force_login(hiring_manager)

    response = client.post(
        extend_url(in_grace), {"ends": in_grace.grace_period_ends.isoformat(), "note": "Why."}
    )

    assert 'data-testid="error-ends"' in page(response)
    assert JobOpening.objects.get(pk=in_grace.pk).grace_period_ends == in_grace.grace_period_ends


def test_the_extend_page_sends_you_back_without_a_grace_period(client, hiring_manager, awaiting):
    client.force_login(hiring_manager)

    response = client.get(extend_url(awaiting))

    assert response.status_code == 302
    assert latest_message(response) == "Backend Developer has no grace period to extend."


def test_the_extend_page_sends_you_back_after_an_auto_cancel(client, hiring_manager, in_grace):
    JobOpening.objects.filter(pk=in_grace.pk).update(grace_expiry_action=AUTO_CANCEL)
    overdue(in_grace)
    client.force_login(hiring_manager)

    response = client.get(extend_url(in_grace))

    assert response.status_code == 302
    assert "can't be extended" in latest_message(response)


def test_the_extend_page_says_an_overdue_opening_stops_being_overdue(
    client, hiring_manager, in_grace
):
    overdue(in_grace)
    client.force_login(hiring_manager)

    response = client.get(extend_url(in_grace))

    assert 'data-testid="extend-clears-overdue"' in page(response)
    assert "Overdue since" in text(response)


# The closure panel


@pytest.mark.parametrize(
    ("user_fixture", "decides"),
    [("admin", True), ("hiring_manager", True), ("recruiter", False), ("interviewer", False)],
)
def test_the_panel_offers_a_grace_period_only_to_deciders(
    client, request, awaiting, user_fixture, decides
):
    client.force_login(request.getfixturevalue(user_fixture))

    html = page(detail(client, awaiting))

    assert ('data-testid="set-grace-period"' in html) is decides
    assert 'data-testid="extend-grace-period"' not in html
    assert 'data-testid="grace-period"' not in html


@pytest.mark.parametrize(
    ("user_fixture", "decides"), [("hiring_manager", True), ("recruiter", False)]
)
def test_during_a_grace_period_the_panel_shows_its_end_and_offers_extend_and_cancel(
    client, request, in_grace, user_fixture, decides
):
    client.force_login(request.getfixturevalue(user_fixture))

    response = detail(client, in_grace)

    html, words = page(response), text(response)
    ends = in_grace.grace_period_ends
    assert 'data-testid="closure-in-grace"' in html
    assert f"Grace period ends {ends:%b} {ends.day}, {ends.year} · 5 days left" in words
    assert "the opening will be flagged as overdue and Hal Manager emailed" in words
    assert 'data-testid="set-grace-period"' not in html
    assert ('data-testid="extend-grace-period"' in html) is decides
    assert ('data-testid="cancel-remaining"' in html) is decides


def test_an_overdue_opening_shows_overdue_and_offers_extend(client, hiring_manager, in_grace):
    overdue(in_grace)
    client.force_login(hiring_manager)

    response = detail(client, in_grace)

    html = page(response)
    assert 'data-testid="closure-overdue"' in html
    assert "these applicants are waiting for a decision" in text(response)
    assert 'data-testid="extend-grace-period"' in html


def test_after_an_auto_cancel_ended_only_cancel_is_offered(client, hiring_manager, in_grace):
    JobOpening.objects.filter(pk=in_grace.pk).update(grace_expiry_action=AUTO_CANCEL)
    overdue(in_grace)
    client.force_login(hiring_manager)

    response = detail(client, in_grace)

    html = page(response)
    assert "its applications were cancelled" in text(response)
    assert 'data-testid="extend-grace-period"' not in html
    assert 'data-testid="set-grace-period"' not in html
    assert 'data-testid="cancel-remaining"' in html


def test_the_history_lists_grace_period_events(client, hiring_manager, awaiting):
    client.force_login(hiring_manager)
    client.post(set_url(awaiting), {"days": "7", "action": FLAG_OVERDUE})
    ends = today() + timedelta(days=9)
    client.post(extend_url(awaiting), {"ends": ends.isoformat(), "note": "More time."})

    response = detail(client, awaiting)

    html, words = page(response), text(response)
    assert 'data-testid="opening-event-grace_period_set"' in html
    assert 'data-testid="opening-event-grace_period_extended"' in html
    assert "Grace period set" in words and "Grace period extended" in words
    assert "Reason: More time." in words
