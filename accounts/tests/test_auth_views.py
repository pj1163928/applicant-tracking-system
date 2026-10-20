import pytest
from django.urls import NoReverseMatch, reverse

pytestmark = pytest.mark.django_db


def test_anonymous_user_is_redirected_to_login(client):
    response = client.get(reverse("accounts:home"))

    assert response.status_code == 302
    assert response.url == f"{reverse('accounts:login')}?next=/"


def test_login_page_is_open_to_anonymous_users(client):
    response = client.get(reverse("accounts:login"))

    assert response.status_code == 200
    assert b"Staff login" in response.content


@pytest.mark.parametrize("path", ["/accounts/signup/", "/accounts/register/", "/signup/"])
def test_there_is_no_signup_url(client, path):
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("name", ["accounts:signup", "accounts:register"])
def test_no_signup_route_is_named(name):
    with pytest.raises(NoReverseMatch):
        reverse(name)


def test_login_page_offers_no_signup_link(client):
    assert b"Sign up" not in client.get(reverse("accounts:login")).content


def test_staff_can_log_in_and_land_on_home(client, recruiter):
    response = client.post(
        reverse("accounts:login"), {"username": "recruiter", "password": "pw"}, follow=True
    )

    assert response.redirect_chain[-1][0] == reverse("accounts:home")
    assert response.context["user"] == recruiter


def test_wrong_password_shows_an_error(client, recruiter):
    response = client.post(reverse("accounts:login"), {"username": "recruiter", "password": "no"})

    assert response.status_code == 200
    assert b"alert-error" in response.content
    assert not response.context["user"].is_authenticated


def test_logout_ends_the_session(client, recruiter):
    client.force_login(recruiter)

    response = client.post(reverse("accounts:logout"))

    assert response.url == reverse("accounts:login")
    assert client.get(reverse("accounts:home")).status_code == 302


@pytest.mark.parametrize(
    ("user_fixture", "name", "role"),
    [
        ("admin", "Ada Admin", "Admin"),
        ("recruiter", "Rae Recruiter", "Recruiter"),
        ("hiring_manager", "Hal Manager", "Hiring Manager"),
        ("interviewer", "Ivy Interviewer", "Interviewer"),
    ],
)
def test_base_layout_shows_name_role_and_logout(client, request, user_fixture, name, role):
    client.force_login(request.getfixturevalue(user_fixture))

    content = client.get(reverse("accounts:home")).content.decode()

    assert f'data-testid="user-name">{name}<' in content
    assert f'data-testid="user-role">{role}<' in content
    assert f'action="{reverse("accounts:logout")}"' in content
    assert "htmx.min.js" in content
    assert "js-theme-toggle" in content


def test_view_only_note_shows_for_interviewers_only(client, interviewer, recruiter):
    client.force_login(interviewer)
    assert b"view-only" in client.get(reverse("accounts:home")).content

    client.force_login(recruiter)
    assert b"view-only" not in client.get(reverse("accounts:home")).content


def test_only_admins_see_the_django_admin_link(client, admin, recruiter):
    admin_url = reverse("admin:index").encode()

    client.force_login(admin)
    assert admin_url in client.get(reverse("accounts:home")).content

    client.force_login(recruiter)
    assert admin_url not in client.get(reverse("accounts:home")).content


def test_layout_has_top_nav_and_small_screen_sidebar(client, recruiter):
    client.force_login(recruiter)

    content = client.get(reverse("accounts:home")).content.decode()

    assert 'id="nav-drawer"' in content
    assert 'data-testid="drawer-open"' in content
    assert 'data-testid="sidebar"' in content
    # The same nav links render in both the top bar and the sidebar.
    assert content.count('aria-current="page"') == 2


def test_login_page_has_no_navigation(client):
    content = client.get(reverse("accounts:login")).content.decode()

    assert 'id="nav-drawer"' not in content
    assert 'id="main"' in content
