"""Changing an opening's designated authority, through its page."""

from html import unescape

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from accounts.roles import RECRUITER
from openings.models import JobOpening, OpeningEvent

pytestmark = pytest.mark.django_db


def page(response) -> str:
    return unescape(response.content.decode())


@pytest.fixture
def opening(make_opening, hiring_manager) -> JobOpening:
    return make_opening("Backend Developer", hiring_manager)


@pytest.fixture
def morgan(make_user):
    return make_user(
        "morgan", RECRUITER, first_name="Morgan", last_name="Patel", email="morgan@example.com"
    )


def url(opening) -> str:
    return reverse("openings:change_authority", args=[opening.pk])


def test_anonymous_users_are_sent_to_log_in(client, opening):
    response = client.get(url(opening))

    assert response.status_code == 302
    assert response.url.startswith(reverse("accounts:login"))


@pytest.mark.parametrize("role", ["hiring_manager", "interviewer", "no_role_user"])
def test_other_roles_are_refused_for_get_and_post(request, client, opening, morgan, role):
    client.force_login(request.getfixturevalue(role))

    assert client.get(url(opening)).status_code == 403
    assert client.post(url(opening), {"authority": morgan.pk}).status_code == 403
    assert JobOpening.objects.get(pk=opening.pk).designated_authority.username == "manager"
    assert not OpeningEvent.objects.exists()


@pytest.mark.parametrize("role", ["admin", "recruiter"])
def test_admins_and_recruiters_change_it_and_see_it_in_the_history(
    request, client, opening, morgan, role, mailoutbox, django_capture_on_commit_callbacks
):
    client.force_login(request.getfixturevalue(role))
    assert client.get(url(opening)).status_code == 200

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(url(opening), {"authority": morgan.pk, "note": "New lead."})

    assert response.status_code == 302
    assert response.url == opening.get_absolute_url()
    assert JobOpening.objects.get(pk=opening.pk).designated_authority == morgan
    assert len(mailoutbox) == 1
    message = [str(m) for m in get_messages(response.wsgi_request)][-1]
    assert message == (
        "Morgan Patel is now the designated authority for Backend Developer, and has been emailed."
    )
    detail = page(client.get(opening.get_absolute_url()))
    assert 'data-testid="opening-event-authority_changed"' in detail
    assert "From Hal Manager to Morgan Patel." in detail


def test_the_choices_leave_out_the_current_authority_and_anyone_ineligible(
    client, admin, opening, morgan, interviewer, make_user
):
    make_user("gone", RECRUITER, first_name="Gil", last_name="Gone", is_active=False)
    client.force_login(admin)

    form = client.get(url(opening)).context["form"]

    choices = set(form.fields["authority"].queryset.values_list("username", flat=True))
    assert choices == {"admin", "morgan"}


@pytest.mark.parametrize("who", ["interviewer", "inactive", "current"])
def test_posting_someone_the_form_never_offers_is_refused(
    request, client, admin, opening, hiring_manager, make_user, who
):
    if who == "inactive":
        target = make_user("gone", RECRUITER, is_active=False)
    elif who == "current":
        target = hiring_manager
    else:
        target = request.getfixturevalue(who)
    client.force_login(admin)

    response = client.post(url(opening), {"authority": target.pk})

    assert response.status_code == 200
    assert response.context["form"].errors["authority"] == [
        "Pick an active Admin, Recruiter or Hiring Manager."
    ]
    assert JobOpening.objects.get(pk=opening.pk).designated_authority == hiring_manager
    assert not OpeningEvent.objects.exists()


def test_a_missing_choice_shows_an_error(client, admin, opening):
    client.force_login(admin)

    response = client.post(url(opening), {"authority": ""})

    assert response.context["form"].errors["authority"] == ["Pick the new designated authority."]


@pytest.mark.parametrize(
    ("role", "shown"),
    [
        ("admin", True),
        ("recruiter", True),
        ("hiring_manager", False),
        ("interviewer", False),
    ],
)
def test_only_those_who_may_change_it_see_the_change_button(request, client, opening, role, shown):
    client.force_login(request.getfixturevalue(role))

    detail = page(client.get(opening.get_absolute_url()))

    assert ('data-testid="authority-change"' in detail) is shown
