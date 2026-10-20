"""Applications on the candidate and opening pages, and who sees "Record application"."""

import pytest
from django.urls import reverse

from applications.models import Application

pytestmark = pytest.mark.django_db

ALL_ROLES = ["admin", "recruiter", "hiring_manager", "interviewer", "no_role_user"]
MANAGERS = {"admin", "recruiter"}


def page(client, user, record) -> str:
    client.force_login(user)
    response = client.get(record.get_absolute_url())
    assert response.status_code == 200
    return response.content.decode()


def test_a_candidates_page_lists_each_application_with_its_stage_and_source(
    client, interviewer, apply, ann, backend, closed_opening, referral, monster, indeed
):
    apply(ann, backend, referral, referred_by="Dana Lee")
    # An older application, through a source retired since, to an opening closed since.
    Application.objects.create(candidate=ann, opening=closed_opening, source=monster)

    content = page(client, interviewer, ann)

    assert content.count('data-testid="application"') == 2
    assert "Backend Developer" in content and "UX Researcher" in content
    assert content.count('data-testid="stage-applied"') == 2
    assert "Referred by Dana Lee" in content
    assert 'badge badge-xs badge-ghost">retired</span>' in content
    assert 'data-testid="status-closed"' in content
    assert 'data-testid="applications-empty"' not in content


def test_an_openings_page_lists_its_applicants(
    client, interviewer, apply, ann, ben, backend, indeed
):
    apply(ann, backend, indeed)
    apply(ben, backend, indeed)

    content = page(client, interviewer, backend)

    assert content.count('data-testid="application"') == 2
    assert "Ann Lee" in content and "Ben Ortiz" in content
    assert reverse("candidates:detail", args=[ann.pk]) in content


def test_an_opening_without_applications_says_so(client, interviewer, backend):
    content = page(client, interviewer, backend)

    assert 'data-testid="applications-empty"' in content


@pytest.mark.parametrize("user_fixture", ALL_ROLES)
def test_only_managers_see_record_and_edit_actions_on_a_candidates_page(
    client, request, user_fixture, apply, ann, backend, qa, indeed
):
    apply(ann, backend, indeed)  # QA Analyst is still open to Ann

    content = page(client, request.getfixturevalue(user_fixture), ann)

    allowed = user_fixture in MANAGERS
    assert ('data-testid="application-add"' in content) is allowed
    assert (f"{reverse('applications:create')}?candidate={ann.pk}" in content) is allowed
    assert ('data-testid="application-edit"' in content) is allowed


def test_a_candidate_with_nowhere_left_to_apply_has_no_record_action(
    client, recruiter, apply, ann, backend, closed_opening, indeed
):
    apply(ann, backend, indeed)

    content = page(client, recruiter, ann)

    assert 'data-testid="application-add"' not in content
    assert "No open openings left for Ann to apply for." in content


def test_with_no_open_openings_at_all_a_new_candidate_has_no_record_action(
    client, recruiter, ann, closed_opening
):
    content = page(client, recruiter, ann)

    assert 'data-testid="application-add"' not in content
    assert 'data-testid="application-add-unavailable"' in content


@pytest.mark.parametrize("user_fixture", ALL_ROLES)
def test_only_managers_see_record_and_edit_actions_on_an_open_openings_page(
    client, request, user_fixture, apply, ann, backend, indeed
):
    apply(ann, backend, indeed)

    content = page(client, request.getfixturevalue(user_fixture), backend)

    allowed = user_fixture in MANAGERS
    assert ('data-testid="application-add"' in content) is allowed
    assert ('data-testid="application-edit"' in content) is allowed
    # Viewers who can't manage applications don't see the closed-opening note either.
    assert 'data-testid="application-add-unavailable"' not in content


def test_a_closed_openings_page_has_no_record_action_even_for_managers(
    client, admin, closed_opening
):
    content = page(client, admin, closed_opening)

    assert 'data-testid="application-add"' not in content
    assert "Closed openings don&#x27;t take new applications." not in content
    assert "Closed openings don't take new applications." in content
