"""Archiving, unarchiving and permanently deleting candidates, through their pages."""

import re
from html import unescape

import pytest
from django.contrib.auth.models import Permission
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from applications.models import Application, StageChange
from applications.stages import Stage
from candidates.models import Candidate

pytestmark = pytest.mark.django_db

ALL_ROLES = ["admin", "recruiter", "hiring_manager", "interviewer", "no_role_user"]
LIST_URL = reverse("candidates:list")
HTMX = {"HTTP_HX_REQUEST": "true"}


def page(response) -> str:
    return unescape(response.content.decode())


def text(response) -> str:
    """The page's words without tags, with runs of whitespace made single spaces."""
    return " ".join(re.sub(r"<[^>]+>", " ", page(response)).split())


def message_texts(response) -> list[str]:
    return [str(m) for m in get_messages(response.wsgi_request)]


def archive(candidate: Candidate) -> None:
    """Archive directly in the database, for setting up a test."""
    Candidate.objects.filter(pk=candidate.pk).update(is_archived=True, archived_at=timezone.now())
    candidate.refresh_from_db()


@pytest.fixture
def ann(db) -> Candidate:
    return Candidate.objects.create(first_name="Ann", last_name="Lee", email="ann@example.com")


def archived_state(candidate: Candidate) -> tuple[bool, bool]:
    fresh = Candidate.objects.get(pk=candidate.pk)
    return fresh.is_archived, fresh.archived_at is not None


# Archive and unarchive


@pytest.mark.parametrize(
    ("user_fixture", "allowed"),
    [
        ("admin", True),
        ("recruiter", True),
        ("hiring_manager", False),
        ("interviewer", False),
        ("no_role_user", False),
    ],
)
def test_only_recruiters_and_admins_can_archive_and_unarchive(
    client, request, kai, user_fixture, allowed
):
    client.force_login(request.getfixturevalue(user_fixture))

    archived = client.post(reverse("candidates:archive", args=[kai.pk]))
    state_after_archive = archived_state(kai)
    archive(kai)
    unarchived = client.post(reverse("candidates:unarchive", args=[kai.pk]))

    if allowed:
        assert (archived.status_code, unarchived.status_code) == (302, 302)
        assert state_after_archive == (True, True)
        assert archived_state(kai) == (False, False)
    else:
        assert (archived.status_code, unarchived.status_code) == (403, 403)
        assert state_after_archive == (False, False)
        assert archived_state(kai) == (True, True)


@pytest.mark.parametrize("name", ["candidates:archive", "candidates:unarchive"])
def test_archive_and_unarchive_take_posts_only(client, recruiter, kai, name):
    client.force_login(recruiter)

    assert client.get(reverse(name, args=[kai.pk])).status_code == 405


def test_archiving_returns_to_the_candidate_with_a_message(client, recruiter, kai):
    client.force_login(recruiter)

    response = client.post(reverse("candidates:archive", args=[kai.pk]), follow=True)

    html = page(response)
    assert response.redirect_chain == [(kai.get_absolute_url(), 302)]
    assert "Archived Kai Moreno. They're hidden from the candidate list" in html
    assert 'data-testid="archived-banner"' in html
    assert 'data-testid="candidate-unarchive"' in html
    assert 'data-testid="candidate-archive"' not in html


def test_archiving_with_an_active_application_is_refused_with_its_reason(
    client, recruiter, kai, backend, application_at
):
    application_at(kai, backend, Stage.INTERVIEW)
    client.force_login(recruiter)

    response = client.post(reverse("candidates:archive", args=[kai.pk]))

    assert response.url == kai.get_absolute_url()
    assert message_texts(response) == [
        "Kai Moreno has an active application, so they can't be archived. "
        "Move it to Hired, Rejected or Withdrawn first."
    ]
    assert archived_state(kai) == (False, False)


def test_the_page_hides_archive_and_says_why_while_an_application_is_active(
    client, recruiter, kai, backend, application_at
):
    application_at(kai, backend, Stage.APPLIED)
    client.force_login(recruiter)

    html = page(client.get(kai.get_absolute_url()))

    assert 'data-testid="candidate-archive"' not in html
    assert 'data-testid="archive-blocked"' in html
    assert "Kai Moreno has an active application" in html


def test_unarchiving_returns_to_the_candidate_with_a_message(client, admin, kai):
    archive(kai)
    client.force_login(admin)

    response = client.post(reverse("candidates:unarchive", args=[kai.pk]), follow=True)

    html = page(response)
    assert "Unarchived Kai Moreno. They can apply for openings again." in html
    assert 'data-testid="archived-banner"' not in html
    assert 'data-testid="candidate-archive"' in html


@pytest.mark.parametrize("user_fixture", ["hiring_manager", "interviewer"])
def test_view_only_roles_see_no_archive_controls(client, request, kai, user_fixture):
    client.force_login(request.getfixturevalue(user_fixture))

    html = page(client.get(kai.get_absolute_url()))
    archive(kai)
    archived_html = page(client.get(kai.get_absolute_url()))

    assert 'data-testid="candidate-archive"' not in html
    assert 'data-testid="candidate-unarchive"' not in archived_html
    assert 'data-testid="archived-banner"' in archived_html


def test_an_archived_candidate_offers_no_record_application(client, recruiter, kai, backend):
    archive(kai)
    client.force_login(recruiter)

    html = page(client.get(kai.get_absolute_url()))

    assert 'data-testid="application-add"' not in html
    assert "Unarchive Kai to record a new application." in html


def test_an_archived_candidates_application_still_shows_on_the_opening_page(
    client, interviewer, kai, backend, application_at
):
    application_at(kai, backend, Stage.WITHDRAWN)
    archive(kai)
    client.force_login(interviewer)

    html = page(client.get(backend.get_absolute_url()))

    assert "Kai Moreno" in html
    assert 'data-testid="archived-badge"' in html


# The list and "Show archived"


def names(response) -> list[str]:
    return [c.full_name for c in response.context["candidates"]]


def test_archived_candidates_are_hidden_from_the_list_by_default(client, interviewer, ann, kai):
    archive(kai)
    client.force_login(interviewer)

    response = client.get(LIST_URL)

    assert names(response) == ["Ann Lee"]
    assert "1 candidate · 1 archived hidden" in text(response)
    assert 'data-testid="show-archived"' in page(response)


def test_show_archived_lists_them_with_a_badge(client, interviewer, ann, kai):
    archive(kai)
    client.force_login(interviewer)

    response = client.get(LIST_URL, {"archived": "1"})

    html = page(response)
    assert names(response) == ["Ann Lee", "Kai Moreno"]
    assert "2 candidates · including 1 archived" in text(response)
    assert html.count('data-testid="archived-badge"') == 1
    assert 'id="show-archived" class="toggle toggle-sm toggle-primary"\n           checked' in html


def test_show_archived_works_with_search_through_htmx(client, recruiter, ann, kai):
    archive(kai)
    client.force_login(recruiter)

    hidden = client.get(LIST_URL, {"q": "kai"}, **HTMX)
    shown = client.get(LIST_URL, {"q": "kai", "archived": "1"}, **HTMX)

    assert "<html" not in page(shown)
    assert names(hidden) == []
    assert "Archived candidates are hidden; turn on Show archived" in page(hidden)
    assert names(shown) == ["Kai Moreno"]


def test_an_archived_candidate_is_still_reachable_by_url(client, interviewer, kai):
    archive(kai)
    client.force_login(interviewer)

    assert client.get(kai.get_absolute_url()).status_code == 200


# Permanent delete


@pytest.mark.parametrize("user_fixture", ALL_ROLES)
def test_only_admins_can_open_or_post_the_delete_page(
    client, request, kai, backend, application_at, user_fixture
):
    application_at(kai, backend, Stage.REJECTED)
    client.force_login(request.getfixturevalue(user_fixture))
    url = reverse("candidates:delete", args=[kai.pk])

    statuses = (client.get(url).status_code, client.post(url).status_code)

    if user_fixture == "admin":
        assert statuses == (200, 302)
        assert (Candidate.objects.count(), Application.objects.count()) == (0, 0)
    else:
        assert statuses == (403, 403)
        assert (Candidate.objects.count(), Application.objects.count()) == (1, 1)


def test_the_confirmation_page_lists_every_application_and_stage_change(
    client, admin, kai, backend, qa, application_at
):
    application_at(kai, backend, Stage.REJECTED)  # 2 stage changes
    application_at(kai, qa, Stage.APPLIED)  # 1 stage change
    client.force_login(admin)

    html = page(client.get(reverse("candidates:delete", args=[kai.pk])))

    assert "Delete Kai Moreno permanently?" in html
    assert "This can't be undone." in html
    assert 'data-testid="delete-application-count">2<' in html
    assert 'data-testid="delete-stage-change-count">3<' in html
    assert html.count('data-testid="delete-application"') == 2
    assert html.count('data-testid="history-row"') == 3
    assert "Backend Developer" in html and "QA Analyst" in html
    assert "If you might need Kai again, archive them instead." in html
    assert StageChange.objects.count() == 3  # looking deletes nothing


def test_a_candidate_with_no_applications_says_so(client, admin, kai):
    client.force_login(admin)

    html = page(client.get(reverse("candidates:delete", args=[kai.pk])))

    assert 'data-testid="delete-no-applications"' in html


def test_confirming_deletes_and_returns_to_the_list_with_what_was_removed(
    client, admin, kai, backend, application_at
):
    application_at(kai, backend, Stage.REJECTED)
    client.force_login(admin)

    response = client.post(reverse("candidates:delete", args=[kai.pk]))

    assert response.url == LIST_URL
    assert message_texts(response) == [
        "Permanently deleted Kai Moreno, with 1 application and 2 stage changes."
    ]
    assert (Application.objects.count(), StageChange.objects.count()) == (0, 0)


@pytest.mark.parametrize("user_fixture", ALL_ROLES)
def test_only_admins_see_the_delete_link(client, request, kai, user_fixture):
    client.force_login(request.getfixturevalue(user_fixture))

    html = page(client.get(kai.get_absolute_url()))

    assert ('data-testid="candidate-delete"' in html) == (user_fixture == "admin")


# The Django admin


def test_the_django_admin_shows_archive_fields_read_only(client, admin, kai):
    client.force_login(admin)

    html = page(client.get(reverse("admin:candidates_candidate_change", args=[kai.pk])))

    assert 'name="is_archived"' not in html
    assert 'name="archived_at' not in html


def test_the_django_admin_lets_only_admins_delete(client, admin, make_user, kai):
    staff = make_user("staffer", is_staff=True)
    staff.user_permissions.set(Permission.objects.filter(codename__endswith="_candidate"))
    url = reverse("admin:candidates_candidate_delete", args=[kai.pk])

    client.force_login(staff)
    assert client.post(url, {"post": "yes"}).status_code == 403
    assert Candidate.objects.filter(pk=kai.pk).exists()

    client.force_login(admin)
    client.post(url, {"post": "yes"})
    assert not Candidate.objects.filter(pk=kai.pk).exists()
