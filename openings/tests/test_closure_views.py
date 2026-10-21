"""Closing an opening and cancelling its remaining applications, through the pages."""

import re
from html import unescape

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from applications.models import Application, StageChange
from applications.stages import Stage
from notifications.models import CandidateMessage
from openings.models import JobOpening, OpeningEvent
from openings.tests.conftest import close_directly

pytestmark = pytest.mark.django_db

ALL_ROLES = ["admin", "recruiter", "hiring_manager", "interviewer", "no_role_user"]


def page(response) -> str:
    return unescape(response.content.decode())


def text(response) -> str:
    """The page's words without tags, with runs of whitespace made single spaces."""
    return " ".join(re.sub(r"<[^>]+>", " ", page(response)).split())


def message_texts(response) -> list[str]:
    return [str(m) for m in get_messages(response.wsgi_request)]


def latest_message(response) -> str:
    """The newest message; earlier ones stay queued because these tests don't follow redirects."""
    return message_texts(response)[-1]


def close_url(opening) -> str:
    return reverse("openings:close", args=[opening.pk])


def cancel_url(opening) -> str:
    return reverse("openings:cancel_remaining", args=[opening.pk])


def detail(client, opening):
    return client.get(reverse("openings:detail", args=[opening.pk]))


def snapshot(opening):
    return (
        JobOpening.objects.get(pk=opening.pk).status,
        sorted(opening.applications.values_list("pk", "stage")),
        StageChange.objects.count(),
        OpeningEvent.objects.count(),
        CandidateMessage.objects.count(),
    )


@pytest.fixture
def ann(make_candidate):
    return make_candidate("Ann")


@pytest.fixture
def ben(make_candidate):
    return make_candidate("Ben")


@pytest.fixture
def awaiting(backend, hiring_manager, ann, ben, application_at):
    """Backend Developer, closed with Ann at Interview and Ben hired: a decision awaits Hal."""
    application_at(ann, backend, Stage.INTERVIEW)
    application_at(ben, backend, Stage.HIRED)
    close_directly(backend, hiring_manager)
    return backend


# Closing


@pytest.mark.parametrize("user_fixture", ALL_ROLES)
def test_only_admins_recruiters_and_hiring_managers_can_open_or_post_the_close_page(
    client, request, backend, user_fixture
):
    client.force_login(request.getfixturevalue(user_fixture))

    statuses = (
        client.get(close_url(backend)).status_code,
        client.post(close_url(backend)).status_code,
    )

    if user_fixture in ("interviewer", "no_role_user"):
        assert statuses == (403, 403)
        assert JobOpening.objects.get(pk=backend.pk).is_open
        assert OpeningEvent.objects.count() == 0
    else:
        assert statuses == (200, 302)
        assert not JobOpening.objects.get(pk=backend.pk).is_open


def test_anonymous_users_are_sent_to_log_in(client, backend):
    response = client.get(close_url(backend))

    assert response.status_code == 302
    assert response.url.startswith(reverse("accounts:login"))


def test_the_close_page_says_who_will_be_asked_to_decide(
    client, recruiter, backend, ann, application_at
):
    application_at(ann, backend, Stage.SCREENING)
    client.force_login(recruiter)

    response = client.get(close_url(backend))

    words = text(response)
    assert "Close Backend Developer?" in words
    assert "It stops taking new applications." in words
    assert (
        "1 applicant is still in progress, so Hal Manager will be emailed and see this opening "
        "in Needs attention, to decide what happens to them." in words
    )


def test_the_close_page_says_when_nobody_is_in_progress(client, recruiter, backend):
    client.force_login(recruiter)

    html = page(client.get(close_url(backend)))

    assert 'data-testid="close-no-active"' in html
    assert 'data-testid="close-notifies"' not in html


def test_closing_writes_the_event_emails_the_authority_and_says_so(
    client,
    recruiter,
    hiring_manager,
    backend,
    ann,
    application_at,
    django_capture_on_commit_callbacks,
    mailoutbox,
):
    hiring_manager.email = "hal@example.com"
    hiring_manager.save()
    application_at(ann, backend, Stage.SCREENING)
    client.force_login(recruiter)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(close_url(backend), {"note": "Paused until spring."})

    assert response.url == backend.get_absolute_url()
    assert message_texts(response) == [
        "Closed Backend Developer. It no longer takes new applications. 1 applicant still in "
        "progress can keep moving, and Hal Manager has been emailed to decide what happens to them."
    ]
    assert list(backend.events.values_list("kind", "by", "note")) == [
        (OpeningEvent.Kind.CLOSED, recruiter.pk, "Paused until spring.")
    ]
    assert [m.to for m in mailoutbox] == [["hal@example.com"]]


def test_an_authority_who_closes_their_own_opening_is_told_they_decide(
    client, hiring_manager, backend, ann, application_at
):
    application_at(ann, backend, Stage.SCREENING)
    client.force_login(hiring_manager)

    response = client.post(close_url(backend))

    assert message_texts(response)[0].endswith("and you decide what happens to them.")


def test_a_note_over_the_limit_is_refused_and_nothing_closes(client, recruiter, backend):
    client.force_login(recruiter)

    response = client.post(close_url(backend), {"note": "x" * 501})

    assert response.status_code == 200
    assert 'data-testid="error-note"' in page(response)
    assert JobOpening.objects.get(pk=backend.pk).is_open
    assert OpeningEvent.objects.count() == 0


def test_an_already_closed_opening_sends_the_user_back_without_a_second_event(
    client, recruiter, backend
):
    client.force_login(recruiter)
    client.post(close_url(backend))

    get, post = client.get(close_url(backend)), client.post(close_url(backend))

    assert get.url == post.url == backend.get_absolute_url()
    assert latest_message(post) == "Backend Developer is already closed."
    assert backend.events.count() == 1


@pytest.mark.parametrize("user_fixture", ALL_ROLES)
def test_only_opening_managers_see_close_and_only_on_open_openings(
    client, request, backend, hiring_manager, user_fixture
):
    client.force_login(request.getfixturevalue(user_fixture))

    shown_when_open = 'data-testid="opening-close"' in page(detail(client, backend))
    close_directly(backend, hiring_manager)
    shown_when_closed = 'data-testid="opening-close"' in page(detail(client, backend))

    assert shown_when_open is (user_fixture not in ("interviewer", "no_role_user"))
    assert shown_when_closed is False


def test_the_edit_form_can_no_longer_reopen_a_closed_opening(client, recruiter, backend):
    close_directly(backend, recruiter)
    client.force_login(recruiter)

    client.post(
        reverse("openings:update", args=[backend.pk]),
        {
            "title": "Backend Developer",
            "department": "Engineering",
            "status": "open",
            "description": "Still closed.",
        },
    )

    backend.refresh_from_db()
    assert backend.description == "Still closed."
    assert not backend.is_open


# The closure panel and Cancel now


@pytest.mark.parametrize(
    ("user_fixture", "decides"),
    [
        ("admin", True),
        ("hiring_manager", True),  # Hal is the authority
        ("recruiter", False),  # can close, but not decide
        ("interviewer", False),
        ("no_role_user", False),
    ],
)
def test_the_closure_panel_shows_decision_actions_only_to_those_who_may_decide(
    client, request, awaiting, user_fixture, decides
):
    client.force_login(request.getfixturevalue(user_fixture))

    response = detail(client, awaiting)

    html, words = page(response), text(response)
    assert 'data-testid="closure-panel"' in html
    assert "1 applicant still in progress" in words
    assert ('data-testid="cancel-remaining"' in html) is decides
    assert ('data-testid="closure-waiting"' in html) is not decides


def test_no_closure_panel_without_active_applications(
    client, hiring_manager, backend, ben, application_at
):
    application_at(ben, backend, Stage.HIRED)
    close_directly(backend, hiring_manager)
    client.force_login(hiring_manager)

    assert 'data-testid="closure-panel"' not in page(detail(client, backend))


@pytest.mark.parametrize("user_fixture", ["recruiter", "interviewer", "no_role_user"])
def test_those_who_cant_decide_get_403_for_get_and_post_and_nothing_changes(
    client, request, awaiting, user_fixture
):
    client.force_login(request.getfixturevalue(user_fixture))
    before = snapshot(awaiting)

    statuses = (
        client.get(cancel_url(awaiting)).status_code,
        client.post(cancel_url(awaiting)).status_code,
    )

    assert statuses == (403, 403)
    assert snapshot(awaiting) == before


def test_the_cancel_page_lists_who_will_be_rejected_and_emailed(client, hiring_manager, awaiting):
    client.force_login(hiring_manager)

    response = client.get(cancel_url(awaiting))

    words = text(response)
    assert "Cancel 1 remaining application?" in words
    assert page(response).count('data-testid="cancel-applicant"') == 1
    assert "Ann Test" in words and "Ben Test" not in words
    assert 'moves to Rejected with the note "Position closed."' in words


def test_cancelling_rejects_emails_and_says_so_and_a_repeat_changes_nothing(
    client, hiring_manager, awaiting, django_capture_on_commit_callbacks, mailoutbox
):
    client.force_login(hiring_manager)

    with django_capture_on_commit_callbacks(execute=True):
        first = client.post(cancel_url(awaiting))
    after_first = snapshot(awaiting)
    with django_capture_on_commit_callbacks(execute=True):
        again = client.post(cancel_url(awaiting))  # a double submission

    assert first.url == awaiting.get_absolute_url()
    assert message_texts(first) == [
        "Cancelled 1 application for Backend Developer. The candidate has been emailed that the "
        "position closed."
    ]
    assert latest_message(again) == (
        "Nothing to cancel: no applicants for Backend Developer are in progress."
    )
    assert snapshot(awaiting) == after_first
    assert [m.to for m in mailoutbox] == [["ann@example.com"]]
    assert sorted(awaiting.applications.values_list("stage", flat=True)) == [
        Stage.HIRED,
        Stage.REJECTED,
    ]


def test_a_recruiter_who_is_the_authority_can_cancel_through_the_page(
    client, skilled_opening, authority, ann, application_at
):
    application = application_at(ann, skilled_opening, Stage.APPLIED)
    close_directly(skilled_opening, authority)
    client.force_login(authority)

    assert 'data-testid="cancel-remaining"' in page(detail(client, skilled_opening))
    client.post(cancel_url(skilled_opening))

    assert Application.objects.get(pk=application.pk).stage == Stage.REJECTED


def test_cancelling_an_open_opening_is_refused_with_a_message(
    client, hiring_manager, backend, ann, application_at
):
    application_at(ann, backend, Stage.INTERVIEW)
    client.force_login(hiring_manager)
    before = snapshot(backend)

    get, post = client.get(cancel_url(backend)), client.post(cancel_url(backend))

    assert get.url == post.url == backend.get_absolute_url()
    assert latest_message(post) == (
        "Backend Developer is open. Close it before cancelling its applications."
    )
    assert snapshot(backend) == before


def test_the_cancel_page_sends_you_back_when_nobody_is_left(client, hiring_manager, awaiting):
    client.force_login(hiring_manager)
    client.post(cancel_url(awaiting))

    response = client.get(cancel_url(awaiting))

    assert response.url == awaiting.get_absolute_url()
    assert latest_message(response) == "No applicants for Backend Developer are still in progress."


# Event history


def test_the_opening_page_lists_its_events_newest_first(
    client, interviewer, hiring_manager, awaiting
):
    awaiting.events.filter(kind=OpeningEvent.Kind.CLOSED).update(note="Budget moved.")
    client.force_login(hiring_manager)
    client.post(cancel_url(awaiting))
    client.force_login(interviewer)  # every role may see the history

    response = detail(client, awaiting)

    html, words = page(response), text(response)
    assert html.index('data-testid="opening-event-applications_cancelled"') < html.index(
        'data-testid="opening-event-closed"'
    )
    assert "Remaining applications cancelled Hal Manager ·" in words
    assert "Closed Hal Manager ·" in words
    assert "Budget moved." in words


def test_an_opening_with_no_events_says_so(client, recruiter, backend):
    client.force_login(recruiter)

    assert 'data-testid="opening-events-empty"' in page(detail(client, backend))


# Moves after closing


@pytest.mark.parametrize(
    ("start", "to_stage"), [(Stage.APPLIED, Stage.SCREENING), (Stage.OFFER, Stage.HIRED)]
)
def test_the_board_still_moves_a_closed_openings_applicants(
    client, hiring_manager, backend, ann, application_at, start, to_stage
):
    application = application_at(ann, backend, start)
    close_directly(backend, hiring_manager)
    client.force_login(hiring_manager)

    response = client.post(
        reverse("applications:move", args=[application.pk]),
        {"to_stage": to_stage, "expected_stage": start},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert Application.objects.get(pk=application.pk).stage == to_stage
