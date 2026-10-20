import re

import pytest
from django.urls import reverse

from openings.models import JobOpening

pytestmark = pytest.mark.django_db

ALL_ROLES = ["admin", "recruiter", "hiring_manager", "interviewer", "no_role_user"]


@pytest.fixture
def openings(make_opening, hiring_manager, recruiter, admin):
    """Three openings with three different designated authorities; one is closed."""
    return {
        "backend": make_opening("Backend Developer", hiring_manager, location="Remote"),
        "ux": make_opening(
            "UX Researcher", hiring_manager, department="Design", status=JobOpening.Status.CLOSED
        ),
        "data": make_opening("Data Engineer", recruiter, department="Data"),
        "design": make_opening("Product Designer", admin, department="Design"),
    }


def post_data(**overrides) -> dict:
    return {
        "title": "QA Analyst",
        "department": "Engineering",
        "location": "",
        "status": "open",
        "description": "Plan and automate testing.",
    } | overrides


def snapshot():
    return list(
        JobOpening.objects.order_by("pk").values_list(
            "title", "department", "location", "status", "description", "designated_authority"
        )
    )


def row_titles(response) -> list[str]:
    return [o.title for o in response.context["openings"]]


def tab_counts(content: str) -> dict[str, str]:
    """The count badge on each My openings / All tab, keyed by scope."""
    found = re.findall(
        r'data-testid="scope-(mine|all)">\s*[\w ]+ <span class="badge[^"]*">(\d+)</span>', content
    )
    return dict(found)


@pytest.mark.parametrize(
    ("user_fixture", "allowed"),
    [
        ("admin", True),
        ("recruiter", True),
        ("hiring_manager", True),
        ("interviewer", False),
        ("no_role_user", False),
    ],
)
def test_only_admins_recruiters_and_hiring_managers_can_create_or_edit_openings(
    client, request, user_fixture, allowed, openings, hiring_manager
):
    before = snapshot()
    client.force_login(request.getfixturevalue(user_fixture))
    backend = openings["backend"]
    create_url = reverse("openings:create")
    edit_url = reverse("openings:update", args=[backend.pk])

    statuses = [
        client.get(create_url).status_code,
        client.post(create_url, post_data(designated_authority=hiring_manager.pk)).status_code,
        client.get(edit_url).status_code,
        client.post(edit_url, post_data(title="Senior Backend Developer")).status_code,
    ]

    if allowed:
        assert statuses == [200, 302, 200, 302]
        assert JobOpening.objects.filter(title="QA Analyst").exists()
        backend.refresh_from_db()
        assert backend.title == "Senior Backend Developer"
    else:
        assert statuses == [403] * 4
        assert snapshot() == before


@pytest.mark.parametrize("ineligible", ["interviewer", "no_role_user", "inactive_manager"])
def test_a_hand_made_create_post_naming_an_ineligible_authority_is_refused(
    client, request, recruiter, ineligible
):
    client.force_login(recruiter)
    target = request.getfixturevalue(ineligible)

    response = client.post(reverse("openings:create"), post_data(designated_authority=target.pk))

    assert response.status_code == 200  # the form is shown again with the error
    assert JobOpening.objects.count() == 0
    errors = response.context["form"].errors["designated_authority"]
    assert errors == ["Pick an active Admin, Recruiter or Hiring Manager."]
    assert 'data-testid="error-designated_authority"' in response.content.decode()


def test_creating_an_opening_saves_it_and_redirects_to_its_page(client, hiring_manager):
    client.force_login(hiring_manager)

    response = client.post(
        reverse("openings:create"), post_data(designated_authority=hiring_manager.pk), follow=True
    )

    opening = JobOpening.objects.get()
    assert response.redirect_chain == [(opening.get_absolute_url(), 302)]
    assert opening.designated_authority == hiring_manager
    assert opening.status == JobOpening.Status.OPEN
    assert "Created QA Analyst." in response.content.decode()


def test_the_create_page_lists_only_eligible_authorities(
    client, recruiter, admin, hiring_manager, interviewer, no_role_user, inactive_manager
):
    client.force_login(recruiter)

    choices = client.get(reverse("openings:create")).context["form"].fields["designated_authority"]

    assert set(choices.queryset) == {admin, recruiter, hiring_manager}


def test_editing_never_changes_the_designated_authority(client, recruiter, openings):
    backend = openings["backend"]
    client.force_login(recruiter)

    client.post(
        reverse("openings:update", args=[backend.pk]),
        post_data(title="Backend Developer", designated_authority=recruiter.pk),
    )

    backend.refresh_from_db()
    assert backend.designated_authority.username == "manager"


def test_the_edit_page_shows_the_authority_read_only_and_the_saved_title_on_errors(
    client, recruiter, openings
):
    backend = openings["backend"]
    client.force_login(recruiter)

    response = client.post(reverse("openings:update", args=[backend.pk]), post_data(title=""))

    content = response.content.decode()
    assert response.status_code == 200
    assert 'data-testid="authority-readonly"' in content
    assert "Hal Manager" in content
    assert "Edit Backend Developer" in content
    assert 'name="designated_authority"' not in content


@pytest.mark.parametrize(
    ("user_fixture", "default_scope", "expected_titles"),
    [
        ("hiring_manager", "mine", ["Backend Developer", "UX Researcher"]),
        (
            "recruiter",
            "all",
            ["Backend Developer", "Data Engineer", "Product Designer", "UX Researcher"],
        ),
        (
            "admin",
            "all",
            ["Backend Developer", "Data Engineer", "Product Designer", "UX Researcher"],
        ),
        (
            "interviewer",
            "all",
            ["Backend Developer", "Data Engineer", "Product Designer", "UX Researcher"],
        ),
        (
            "no_role_user",
            "all",
            ["Backend Developer", "Data Engineer", "Product Designer", "UX Researcher"],
        ),
    ],
)
def test_the_list_starts_on_the_roles_default_scope(
    client, request, openings, user_fixture, default_scope, expected_titles
):
    client.force_login(request.getfixturevalue(user_fixture))

    response = client.get(reverse("openings:list"))

    assert response.context["scope"] == default_scope
    assert row_titles(response) == expected_titles  # open first, then closed
    assert f'data-testid="scope-{default_scope}"' in response.content.decode()


def test_the_toggle_works_both_ways(client, hiring_manager, recruiter, openings):
    client.force_login(hiring_manager)
    assert len(row_titles(client.get(reverse("openings:list"), {"show": "all"}))) == 4
    assert row_titles(client.get(reverse("openings:list"), {"show": "mine"})) == [
        "Backend Developer",
        "UX Researcher",
    ]

    client.force_login(recruiter)
    assert row_titles(client.get(reverse("openings:list"), {"show": "mine"})) == ["Data Engineer"]
    assert len(row_titles(client.get(reverse("openings:list"), {"show": "all"}))) == 4


def test_an_unknown_scope_falls_back_to_the_default(client, hiring_manager, openings):
    client.force_login(hiring_manager)

    response = client.get(reverse("openings:list"), {"show": "everything"})

    assert response.context["scope"] == "mine"


def test_my_openings_shows_counts_and_a_way_to_see_all(client, hiring_manager, openings):
    client.force_login(hiring_manager)

    content = client.get(reverse("openings:list")).content.decode()

    assert "Showing 2 of 4 openings" in content
    assert 'data-testid="show-all"' in content
    assert tab_counts(content) == {"mine": "2", "all": "4"}


def test_an_interviewers_my_openings_is_empty_and_says_why(client, interviewer, openings):
    client.force_login(interviewer)

    content = client.get(reverse("openings:list"), {"show": "mine"}).content.decode()

    assert "You aren't the designated authority for any openings." in content


@pytest.mark.parametrize("user_fixture", ALL_ROLES)
def test_my_openings_never_hides_anything(client, request, user_fixture, openings):
    client.force_login(request.getfixturevalue(user_fixture))

    all_titles = row_titles(client.get(reverse("openings:list"), {"show": "all"}))
    detail_statuses = [
        client.get(reverse("openings:detail", args=[o.pk])).status_code for o in openings.values()
    ]

    assert sorted(all_titles) == sorted(o.title for o in openings.values())
    assert detail_statuses == [200] * len(openings)


def test_htmx_toggle_returns_only_the_results_partial(client, hiring_manager, openings):
    client.force_login(hiring_manager)

    response = client.get(reverse("openings:list"), {"show": "all"}, HTTP_HX_REQUEST="true")

    content = response.content.decode()
    assert "<html" not in content
    assert 'data-testid="opening-list"' in content
    assert "HX-Request" in response["Vary"]


def test_an_htmx_history_restore_gets_the_full_page(client, hiring_manager, openings):
    client.force_login(hiring_manager)

    response = client.get(
        reverse("openings:list"), HTTP_HX_REQUEST="true", HTTP_HX_HISTORY_RESTORE_REQUEST="true"
    )

    assert "<html" in response.content.decode()


def test_each_row_shows_its_designated_authority_and_marks_your_own(
    client, hiring_manager, openings
):
    client.force_login(hiring_manager)

    content = client.get(reverse("openings:list"), {"show": "all"}).content.decode()

    for name in ["Hal Manager", "Rae Recruiter", "Ada Admin"]:
        assert name in content
    assert content.count('data-testid="authority"') == 4
    assert content.count('data-testid="authority-you"') == 2  # Backend Developer and UX Researcher


def test_the_detail_page_shows_the_details_and_the_authority(client, interviewer, openings):
    client.force_login(interviewer)

    content = client.get(reverse("openings:detail", args=[openings["ux"].pk])).content.decode()

    assert "UX Researcher" in content
    assert "Design" in content
    assert "No location given" in content
    assert 'data-testid="status-closed"' in content
    assert 'data-testid="authority-panel"' in content
    assert "Hal Manager" in content and "Hiring Manager" in content


def test_the_detail_page_tells_the_authority_it_is_theirs(client, hiring_manager, openings):
    client.force_login(hiring_manager)

    content = client.get(reverse("openings:detail", args=[openings["backend"].pk])).content.decode()

    assert "You make this opening's offer and closure decisions." in content


@pytest.mark.parametrize(
    ("user_fixture", "sees_actions"),
    [
        ("admin", True),
        ("recruiter", True),
        ("hiring_manager", True),
        ("interviewer", False),
        ("no_role_user", False),
    ],
)
def test_create_and_edit_buttons_show_only_for_those_who_can_use_them(
    client, request, user_fixture, sees_actions, openings
):
    client.force_login(request.getfixturevalue(user_fixture))

    list_page = client.get(reverse("openings:list")).content.decode()
    detail_page = client.get(
        reverse("openings:detail", args=[openings["backend"].pk])
    ).content.decode()

    assert ('data-testid="opening-add"' in list_page) is sees_actions
    assert ('data-testid="opening-edit"' in detail_page) is sees_actions


def test_anonymous_users_are_sent_to_login(client, openings):
    for url in [
        reverse("openings:list"),
        reverse("openings:create"),
        reverse("openings:detail", args=[openings["backend"].pk]),
        reverse("openings:update", args=[openings["backend"].pk]),
    ]:
        response = client.get(url)
        assert response.status_code == 302
        assert response["Location"].startswith("/accounts/login/")


def test_the_nav_links_to_openings_and_marks_it_current(client, interviewer):
    client.force_login(interviewer)

    content = client.get(reverse("openings:list")).content.decode()

    assert f'href="{reverse("openings:list")}" class="menu-active' in content


def test_the_django_admin_offers_only_eligible_authorities(
    client, admin, recruiter, hiring_manager, interviewer, no_role_user
):
    client.force_login(admin)

    response = client.get(reverse("admin:openings_jobopening_add"))

    field = response.context["adminform"].form.fields["designated_authority"]
    assert set(field.queryset) == {admin, recruiter, hiring_manager}
