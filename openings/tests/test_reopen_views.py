"""Reopening an opening and restoring its cancelled applicants, through the pages."""

import re
from html import unescape

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from applications.models import Application, StageChange
from applications.stages import Stage
from candidates.models import Candidate
from notifications.models import CandidateMessage
from openings.models import JobOpening, OpeningEvent
from openings.tests.conftest import cancel_directly, close_directly, reopen_directly

pytestmark = pytest.mark.django_db

ALL_ROLES = ["admin", "recruiter", "hiring_manager", "interviewer", "no_role_user"]


def page(response) -> str:
    return unescape(response.content.decode())


def text(response) -> str:
    """The page's words without tags, with runs of whitespace made single spaces."""
    return " ".join(re.sub(r"<[^>]+>", " ", page(response)).split())


def latest_message(response) -> str:
    return [str(m) for m in get_messages(response.wsgi_request)][-1]


def reopen_url(opening) -> str:
    return reverse("openings:reopen", args=[opening.pk])


def restore_url(opening) -> str:
    return reverse("openings:restore", args=[opening.pk])


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
def cancelled(backend, recruiter, make_candidate, application_at):
    """Backend Developer (Hal's), closed with Dev (Screening) and Lena (Interview) cancelled."""
    dev = application_at(make_candidate("Dev"), backend, Stage.SCREENING)
    lena = application_at(make_candidate("Lena"), backend, Stage.INTERVIEW)
    closure = close_directly(backend, recruiter)
    cancel_directly(dev, closure, recruiter)
    cancel_directly(lena, closure, recruiter)
    return {"dev": dev, "lena": lena}


@pytest.fixture
def reopened(backend, cancelled, recruiter):
    reopen_directly(backend, recruiter)
    return cancelled


def archive(application) -> None:
    Candidate.objects.filter(pk=application.candidate_id).update(
        is_archived=True, archived_at=timezone.now()
    )


# Reopening


@pytest.mark.parametrize("role", ["interviewer", "no_role_user"])
def test_reopening_is_refused_with_403_for_get_and_post(client, request, backend, recruiter, role):
    close_directly(backend, recruiter)
    client.force_login(request.getfixturevalue(role))
    before = snapshot(backend)

    assert client.get(reopen_url(backend)).status_code == 403
    assert client.post(reopen_url(backend), {"note": ""}).status_code == 403
    assert snapshot(backend) == before


def test_anonymous_users_are_sent_to_log_in(client, backend):
    response = client.get(reopen_url(backend))

    assert response.status_code == 302
    assert response.url.startswith("/accounts/login/")


def test_the_reopen_page_says_what_happens(client, backend, cancelled, recruiter):
    client.force_login(recruiter)

    response = client.get(reopen_url(backend))

    assert response.status_code == 200
    words = text(response)
    assert "Reopen Backend Developer?" in words
    assert "It takes new applications again." in words
    assert (
        "2 applicants cancelled when it closed can be restored to where they were. "
        "Hal Manager, the designated authority, will see it in Needs attention to choose who."
    ) in words


def test_reopening_an_open_opening_sends_you_back(client, backend, recruiter):
    client.force_login(recruiter)

    response = client.get(reopen_url(backend))

    assert response.status_code == 302
    assert latest_message(response) == "Backend Developer is already open."


def test_a_recruiter_reopens_and_leaves_the_restore_choice_to_the_authority(
    client, backend, cancelled, recruiter
):
    client.force_login(recruiter)

    response = client.post(reopen_url(backend), {"note": "Budget approved."})

    assert response.status_code == 302
    assert response.url == backend.get_absolute_url()
    assert JobOpening.objects.get(pk=backend.pk).is_open
    assert latest_message(response) == (
        "Reopened Backend Developer. It takes new applications again. Hal Manager will see it "
        "in Needs attention, to choose which of the 2 cancelled applicants to restore."
    )
    event = backend.events.first()
    assert (event.kind, event.by, event.note) == (
        OpeningEvent.Kind.REOPENED,
        recruiter,
        "Budget approved.",
    )


def test_a_decider_who_reopens_goes_straight_on_to_choose_who_to_restore(
    client, backend, cancelled, hiring_manager
):
    client.force_login(hiring_manager)

    response = client.post(reopen_url(backend), {"note": ""})

    assert response.url == restore_url(backend)
    assert latest_message(response).endswith("Now choose who to restore.")


def test_reopening_with_nobody_to_restore_just_reopens(client, backend, recruiter, hiring_manager):
    close_directly(backend, recruiter)
    client.force_login(hiring_manager)

    response = client.post(reopen_url(backend), {"note": ""})

    assert response.url == backend.get_absolute_url()
    assert latest_message(response) == (
        "Reopened Backend Developer. It takes new applications again."
    )


@pytest.mark.parametrize("role", ALL_ROLES)
def test_only_opening_managers_see_reopen_and_only_while_it_is_closed(
    client, request, backend, recruiter, role
):
    client.force_login(request.getfixturevalue(role))
    assert 'data-testid="opening-reopen"' not in page(detail(client, backend))

    close_directly(backend, recruiter)

    shown = 'data-testid="opening-reopen"' in page(detail(client, backend))
    assert shown is (role in ("admin", "recruiter", "hiring_manager"))


# Restoring


@pytest.mark.parametrize("role", ["recruiter", "interviewer", "no_role_user"])
def test_restoring_is_refused_with_403_for_get_and_post(client, request, backend, reopened, role):
    client.force_login(request.getfixturevalue(role))
    before = snapshot(backend)

    assert client.get(restore_url(backend)).status_code == 403
    data = {"applications": [reopened["dev"].pk], "decision": "restore"}
    assert client.post(restore_url(backend), data).status_code == 403
    assert snapshot(backend) == before


def test_the_restore_page_lists_each_cancelled_applicant_with_their_stage(
    client, backend, reopened, hiring_manager
):
    client.force_login(hiring_manager)

    response = client.get(restore_url(backend))

    assert response.status_code == 200
    words = text(response)
    assert "Dev Test Dev@example.com Rejected Screening".lower() in words.lower()
    assert "Lena Test Lena@example.com Rejected Interview".lower() in words.lower()
    assert page(response).count('name="applications"') == 2
    assert 'data-testid="confirm-restore"' in page(response)


def test_archived_candidates_are_shown_but_disabled(client, backend, reopened, hiring_manager):
    archive(reopened["lena"])
    client.force_login(hiring_manager)

    response = client.get(restore_url(backend))

    html = page(response)
    lena_box = re.search(rf'<input[^>]*data-testid="restore-checkbox-{reopened["lena"].pk}"', html)
    dev_box = re.search(rf'<input[^>]*data-testid="restore-checkbox-{reopened["dev"].pk}"', html)
    assert " disabled" in html[lena_box.start() : lena_box.end()]
    assert " disabled" not in html[dev_box.start() : dev_box.end()]
    assert "Archived; unarchive first" in text(response)


def test_posting_an_archived_candidate_directly_is_refused(
    client, backend, reopened, hiring_manager
):
    archive(reopened["lena"])
    client.force_login(hiring_manager)
    before = snapshot(backend)

    response = client.post(
        restore_url(backend),
        {"applications": [reopened["dev"].pk, reopened["lena"].pk], "decision": "restore"},
    )

    assert response.status_code == 200
    assert "Only applicants listed here who can be restored can be ticked." in text(response)
    assert snapshot(backend) == before


def test_restoring_ticked_applicants_puts_them_back_and_emails_them(
    client, backend, reopened, hiring_manager, mailoutbox, django_capture_on_commit_callbacks
):
    client.force_login(hiring_manager)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            restore_url(backend), {"applications": [reopened["dev"].pk], "decision": "restore"}
        )

    assert response.url == backend.get_absolute_url()
    assert latest_message(response) == (
        "Restored 1 applicant to Backend Developer, each at their stage before the closure. "
        "The candidate has been emailed that the position reopened."
    )
    stages = dict(backend.applications.values_list("pk", "stage"))
    assert stages == {reopened["dev"].pk: Stage.SCREENING, reopened["lena"].pk: Stage.REJECTED}
    assert [m.to for m in mailoutbox] == [["dev@example.com"]]


def test_restoring_with_nothing_ticked_asks_you_to_tick_someone(
    client, backend, reopened, hiring_manager
):
    client.force_login(hiring_manager)
    before = snapshot(backend)

    response = client.post(restore_url(backend), {"decision": "restore"})

    assert response.status_code == 200
    assert "Tick at least one applicant, or choose Don't restore anyone." in text(response)
    assert snapshot(backend) == before


def test_dont_restore_anyone_records_the_choice(client, backend, reopened, hiring_manager):
    client.force_login(hiring_manager)

    response = client.post(restore_url(backend), {"decision": "none"})

    assert latest_message(response) == (
        "Recorded that nobody cancelled from Backend Developer will be restored."
    )
    assert backend.events.first().kind == OpeningEvent.Kind.APPLICATIONS_RESTORED
    assert set(backend.applications.values_list("stage", flat=True)) == {Stage.REJECTED}


def test_a_repeated_restore_submission_changes_nothing_more(
    client, backend, reopened, hiring_manager
):
    client.force_login(hiring_manager)
    data = {"applications": [reopened["dev"].pk], "decision": "restore"}
    client.post(restore_url(backend), data)
    before = snapshot(backend)

    response = client.post(restore_url(backend), data)

    assert response.status_code == 200  # Dev is no longer a choice, so the form refuses
    assert snapshot(backend) == before


def test_the_restore_page_sends_you_back_while_the_opening_is_closed(
    client, backend, cancelled, hiring_manager
):
    client.force_login(hiring_manager)

    response = client.get(restore_url(backend))

    assert response.status_code == 302
    assert latest_message(response) == (
        "Backend Developer is closed. Reopen it before restoring its applicants."
    )


def test_the_restore_page_sends_you_back_when_nobody_is_left(
    client, backend, recruiter, hiring_manager
):
    close_directly(backend, recruiter)
    reopen_directly(backend, recruiter)
    client.force_login(hiring_manager)

    response = client.get(restore_url(backend))

    assert response.status_code == 302
    assert "is waiting to be restored" in latest_message(response)


# The opening page's restore panel


def test_the_restore_panel_offers_deciders_the_choice(client, backend, reopened, hiring_manager):
    client.force_login(hiring_manager)

    response = detail(client, backend)

    assert 'data-testid="restore-panel"' in page(response)
    assert 'data-testid="choose-restore"' in page(response)
    assert "2 cancelled applicants can be restored" in text(response)


def test_others_see_the_restore_panel_without_the_action(client, backend, reopened, recruiter):
    client.force_login(recruiter)

    response = detail(client, backend)

    assert 'data-testid="choose-restore"' not in page(response)
    assert "Waiting for Hal Manager, the designated authority" in text(response)


def test_the_restore_panel_leaves_once_nobody_is_left_to_restore(
    client, backend, reopened, hiring_manager
):
    client.force_login(hiring_manager)
    data = {"applications": [reopened["dev"].pk, reopened["lena"].pk], "decision": "restore"}
    client.post(restore_url(backend), data)

    assert 'data-testid="restore-panel"' not in page(detail(client, backend))
    assert Application.objects.filter(stage=Stage.REJECTED).count() == 0


def test_the_event_history_lists_reopened_and_restored(client, backend, reopened, hiring_manager):
    client.force_login(hiring_manager)
    client.post(restore_url(backend), {"decision": "none"})

    html = page(detail(client, backend))

    assert 'data-testid="opening-event-reopened"' in html
    assert 'data-testid="opening-event-applications_restored"' in html


def test_the_stage_history_marks_a_restore_with_its_cause(
    client, backend, reopened, hiring_manager
):
    client.force_login(hiring_manager)
    client.post(restore_url(backend), {"applications": [reopened["dev"].pk], "decision": "restore"})

    response = client.get(reverse("applications:history", args=[reopened["dev"].pk]))

    assert "Rejected → Screening Reopening" in text(response)
    assert "Position reopened." in text(response)
