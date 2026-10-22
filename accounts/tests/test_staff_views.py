"""The staff list and the deactivate page (Admins only), and the Django admin's read-only fields."""

from html import unescape

import pytest
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.urls import reverse

from accounts.roles import RECRUITER
from openings.models import JobOpening, OpeningEvent

pytestmark = pytest.mark.django_db

NON_ADMINS = ["recruiter", "hiring_manager", "interviewer", "no_role_user"]


def page(response) -> str:
    return unescape(response.content.decode())


@pytest.fixture
def departing(make_user) -> User:
    return make_user("dana", RECRUITER, first_name="Dana", last_name="Departing")


@pytest.fixture
def openings(make_opening, departing) -> list[JobOpening]:
    return [
        make_opening("Backend Developer", departing),
        make_opening("QA Analyst", departing, status=JobOpening.Status.CLOSED),
    ]


def deactivate_url(user) -> str:
    return reverse("staff:deactivate", args=[user.pk])


def test_anonymous_users_are_sent_to_log_in(client, departing):
    for url in (reverse("staff:list"), deactivate_url(departing)):
        response = client.get(url)
        assert response.status_code == 302
        assert response.url.startswith(reverse("accounts:login"))


@pytest.mark.parametrize("role", NON_ADMINS)
def test_only_admins_reach_the_staff_pages(request, client, departing, openings, role):
    client.force_login(request.getfixturevalue(role))
    backend, qa = openings

    assert client.get(reverse("staff:list")).status_code == 403
    assert client.get(deactivate_url(departing)).status_code == 403
    response = client.post(
        deactivate_url(departing),
        {f"opening_{backend.pk}": request.getfixturevalue("admin").pk},
    )
    assert response.status_code == 403
    assert User.objects.get(pk=departing.pk).is_active is True


@pytest.mark.parametrize(("role", "shown"), [("admin", True), *[(r, False) for r in NON_ADMINS]])
def test_only_admins_see_the_staff_link(request, client, role, shown):
    client.force_login(request.getfixturevalue(role))

    assert ('data-testid="nav-staff"' in page(client.get(reverse("accounts:home")))) is shown


def test_the_list_shows_each_persons_openings_and_who_can_be_deactivated(
    client, admin, departing, openings, make_user
):
    make_user("gone", RECRUITER, is_active=False)
    client.force_login(admin)

    html = page(client.get(reverse("staff:list")))

    dana = html.split('data-testid="staff-dana"')[1].split("</li>")[0]
    assert "2 openings" in dana
    assert 'data-testid="staff-deactivate"' in dana
    gone = html.split('data-testid="staff-gone"')[1].split("</li>")[0]
    assert "Deactivated" in gone
    assert 'data-testid="staff-deactivate"' not in gone
    me = html.split('data-testid="staff-admin"')[1].split("</li>")[0]
    assert 'data-testid="staff-deactivate"' not in me


def test_the_deactivate_page_has_one_picker_per_opening_without_the_person_leaving(
    client, admin, departing, openings, hiring_manager, interviewer
):
    client.force_login(admin)

    form = client.get(deactivate_url(departing)).context["form"]

    backend, qa = openings
    assert set(form.fields) == {f"opening_{backend.pk}", f"opening_{qa.pk}"}
    choices = set(form.fields[f"opening_{qa.pk}"].queryset.values_list("username", flat=True))
    assert choices == {"admin", "manager"}


def test_deactivating_hands_the_openings_over(client, admin, departing, openings, hiring_manager):
    backend, qa = openings
    client.force_login(admin)

    response = client.post(
        deactivate_url(departing),
        {f"opening_{backend.pk}": hiring_manager.pk, f"opening_{qa.pk}": admin.pk},
    )

    assert response.status_code == 302
    assert response.url == reverse("staff:list")
    assert User.objects.get(pk=departing.pk).is_active is False
    assert JobOpening.objects.get(pk=backend.pk).designated_authority == hiring_manager
    assert JobOpening.objects.get(pk=qa.pk).designated_authority == admin
    assert [str(m) for m in get_messages(response.wsgi_request)][-1] == (
        "Deactivated Dana Departing. 2 openings handed over, and each new authority has "
        "been emailed."
    )


def test_someone_with_no_openings_is_deactivated_from_an_empty_form(client, admin, interviewer):
    client.force_login(admin)
    assert 'data-testid="no-openings"' in page(client.get(deactivate_url(interviewer)))

    response = client.post(deactivate_url(interviewer), {})

    assert response.status_code == 302
    assert User.objects.get(pk=interviewer.pk).is_active is False


@pytest.mark.parametrize("pick", ["missing", "interviewer", "departing"])
def test_an_opening_left_without_an_eligible_new_authority_changes_nothing(
    request, client, admin, departing, openings, pick
):
    backend, qa = openings
    data = {f"opening_{backend.pk}": admin.pk}
    if pick != "missing":
        data[f"opening_{qa.pk}"] = request.getfixturevalue(pick).pk
    client.force_login(admin)

    response = client.post(deactivate_url(departing), data)

    assert response.status_code == 200
    assert f"opening_{qa.pk}" in response.context["form"].errors
    assert User.objects.get(pk=departing.pk).is_active is True
    assert set(JobOpening.objects.values_list("designated_authority", flat=True)) == {departing.pk}
    assert not OpeningEvent.objects.exists()


@pytest.mark.parametrize("who", ["self", "inactive"])
def test_self_and_inactive_accounts_are_sent_back_with_a_message(client, admin, make_user, who):
    target = admin if who == "self" else make_user("gone", RECRUITER, is_active=False)
    client.force_login(admin)

    response = client.get(deactivate_url(target))

    assert response.status_code == 302
    assert response.url == reverse("staff:list")
    assert User.objects.get(pk=target.pk).is_active is (who == "self")


def test_the_django_admin_shows_is_active_read_only_on_existing_users(client, admin, departing):
    client.force_login(admin)
    url = reverse("admin:auth_user_change", args=[departing.pk])

    html = page(client.get(url))
    assert 'name="is_active"' not in html
    assert 'name="username"' in html

    client.post(
        url,
        {
            "username": "dana",
            "first_name": "Dana",
            "last_name": "Departing",
            "date_joined_0": "2026-01-01",
            "date_joined_1": "00:00:00",
            "_save": "Save",
        },
    )
    assert User.objects.get(pk=departing.pk).is_active is True


def test_the_django_admin_still_adds_new_users(client, admin):
    client.force_login(admin)

    response = client.post(
        reverse("admin:auth_user_add"),
        {
            "username": "newhire",
            "password1": "a-long-Passw0rd!",
            "password2": "a-long-Passw0rd!",
            "usable_password": "true",
        },
    )

    assert response.status_code == 302
    assert User.objects.get(username="newhire").is_active is True


def test_the_django_admin_shows_an_openings_authority_read_only_once_it_exists(
    client, admin, openings
):
    client.force_login(admin)

    change = page(client.get(reverse("admin:openings_jobopening_change", args=[openings[0].pk])))
    add = page(client.get(reverse("admin:openings_jobopening_add")))

    assert 'name="designated_authority"' not in change
    assert 'name="designated_authority"' in add
