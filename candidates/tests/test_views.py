import pytest
from django.urls import reverse

from candidates.models import Candidate

pytestmark = pytest.mark.django_db


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
def test_only_recruiters_and_admins_can_create_or_edit_candidates(
    client, request, user_fixture, allowed
):
    ann = Candidate.objects.create(first_name="Ann", last_name="Lee", email="ann@x.com")
    # Each role runs in its own rolled-back transaction: nothing from another role's run is here.
    assert list(Candidate.objects.values_list("email", flat=True)) == ["ann@x.com"]
    client.force_login(request.getfixturevalue(user_fixture))
    create_url = reverse("candidates:create")
    edit_url = reverse("candidates:update", args=[ann.pk])

    statuses = [
        client.get(create_url).status_code,
        client.post(
            create_url, {"first_name": "Bo", "last_name": "Diaz", "email": "bo@x.com"}
        ).status_code,
        client.get(edit_url).status_code,
        client.post(
            edit_url, {"first_name": "Ann", "last_name": "Lee-Park", "email": "ann@x.com"}
        ).status_code,
    ]

    names = sorted(c.full_name for c in Candidate.objects.all())
    if allowed:
        assert statuses == [200, 302, 200, 302]
        assert names == ["Ann Lee-Park", "Bo Diaz"]
    else:
        assert statuses == [403, 403, 403, 403]
        assert names == ["Ann Lee"]


ALL_ROLES = ["admin", "recruiter", "hiring_manager", "interviewer", "no_role_user"]


@pytest.fixture
def ann():
    return Candidate.objects.create(
        first_name="Ann", last_name="Lee", email="ann@x.com", phone="555-0101", notes="Keen."
    )


@pytest.mark.parametrize("user_fixture", ALL_ROLES)
def test_every_role_can_browse_the_list_and_open_a_candidate(client, request, user_fixture, ann):
    client.force_login(request.getfixturevalue(user_fixture))

    listing = client.get(reverse("candidates:list"))
    detail = client.get(reverse("candidates:detail", args=[ann.pk]))

    assert listing.status_code == 200
    assert "Ann Lee" in listing.content.decode()
    assert detail.status_code == 200
    content = detail.content.decode()
    assert "ann@x.com" in content
    assert "555-0101" in content
    assert "Keen." in content


@pytest.mark.parametrize(
    ("user_fixture", "shown"),
    [
        ("admin", True),
        ("recruiter", True),
        ("hiring_manager", False),
        ("interviewer", False),
        ("no_role_user", False),
    ],
)
def test_add_and_edit_buttons_show_only_for_candidate_managers(
    client, request, user_fixture, shown, ann
):
    client.force_login(request.getfixturevalue(user_fixture))

    listing = client.get(reverse("candidates:list")).content.decode()
    detail = client.get(reverse("candidates:detail", args=[ann.pk])).content.decode()

    assert ('data-testid="candidate-add"' in listing) is shown
    assert ('data-testid="candidate-edit"' in detail) is shown


@pytest.mark.parametrize(
    "url_name", ["candidates:list", "candidates:create", "candidates:detail", "candidates:update"]
)
def test_anonymous_users_are_sent_to_login(client, ann, url_name):
    args = [ann.pk] if url_name in ("candidates:detail", "candidates:update") else []

    response = client.get(reverse(url_name, args=args))

    assert response.status_code == 302
    assert response.url.startswith(reverse("accounts:login"))


def test_missing_candidate_is_404(client, recruiter):
    client.force_login(recruiter)

    assert client.get(reverse("candidates:detail", args=[999])).status_code == 404
    assert client.get(reverse("candidates:update", args=[999])).status_code == 404


def test_a_new_candidate_has_an_empty_applications_section(client, interviewer, ann):
    client.force_login(interviewer)

    content = client.get(reverse("candidates:detail", args=[ann.pk])).content.decode()

    assert 'data-testid="applications-empty"' in content
    assert "No applications yet." in content


def test_creating_a_candidate_redirects_to_them_with_a_message(client, recruiter):
    client.force_login(recruiter)

    response = client.post(
        reverse("candidates:create"),
        {"first_name": "Bo", "last_name": "Diaz", "email": "Bo@X.com", "phone": "", "notes": ""},
        follow=True,
    )

    bo = Candidate.objects.get()
    assert bo.email == "bo@x.com"
    assert response.redirect_chain == [(bo.get_absolute_url(), 302)]
    assert "Added Bo Diaz." in response.content.decode()


def test_editing_a_candidate_saves_and_redirects_with_a_message(client, admin, ann):
    client.force_login(admin)

    response = client.post(
        reverse("candidates:update", args=[ann.pk]),
        {"first_name": "Ann", "last_name": "Lee", "email": "ann@x.com", "phone": "555-0199"},
        follow=True,
    )

    ann.refresh_from_db()
    assert ann.phone == "555-0199"
    assert ann.notes == ""
    assert response.redirect_chain == [(ann.get_absolute_url(), 302)]
    assert "Saved changes to Ann Lee." in response.content.decode()


def test_duplicate_email_in_another_case_shows_a_clear_error(client, recruiter, ann):
    client.force_login(recruiter)

    response = client.post(
        reverse("candidates:create"),
        {"first_name": "Annie", "last_name": "L", "email": "ANN@X.com"},
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert 'data-testid="error-email"' in content
    assert "A candidate with this email already exists." in content
    assert Candidate.objects.count() == 1


def test_list_search_filters_by_name_and_email(client, interviewer, ann):
    Candidate.objects.create(first_name="Bo", last_name="Diaz", email="bo@other.org")
    client.force_login(interviewer)

    by_name = client.get(reverse("candidates:list"), {"q": "diaz"}).content.decode()
    by_email = client.get(reverse("candidates:list"), {"q": "ann@x"}).content.decode()
    nothing = client.get(reverse("candidates:list"), {"q": "zed"}).content.decode()

    assert "Bo Diaz" in by_name and "Ann Lee" not in by_name
    assert "Ann Lee" in by_email and "Bo Diaz" not in by_email
    assert "1 of 2 candidates match" in by_name
    assert 'data-testid="no-results"' in nothing
    assert "No candidates match" in nothing


def test_htmx_search_returns_only_the_results_partial(client, interviewer, ann):
    client.force_login(interviewer)

    response = client.get(reverse("candidates:list"), {"q": "ann"}, HTTP_HX_REQUEST="true")

    content = response.content.decode()
    assert "<html" not in content
    assert 'data-testid="candidate-row"' in content
    assert "HX-Request" in response["Vary"]


def test_htmx_history_restore_gets_the_full_page(client, interviewer, ann):
    client.force_login(interviewer)

    response = client.get(
        reverse("candidates:list"),
        {"q": "ann"},
        HTTP_HX_REQUEST="true",
        HTTP_HX_HISTORY_RESTORE_REQUEST="true",
    )

    assert "<html" in response.content.decode()


def test_nav_has_a_candidates_link_marked_current_on_candidate_pages(client, interviewer):
    client.force_login(interviewer)

    content = client.get(reverse("candidates:list")).content.decode()

    assert f'href="{reverse("candidates:list")}"' in content
    # Home and Candidates links appear in both menus; only Candidates is current.
    assert content.count('aria-current="page"') == 2
