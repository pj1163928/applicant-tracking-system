import pytest

pytestmark = [pytest.mark.django_db, pytest.mark.urls("accounts.tests.urls")]


@pytest.mark.parametrize("user_fixture", ["interviewer", "no_role_user"])
@pytest.mark.parametrize("method", ["get", "post"])
def test_role_check_refuses_view_only_users_with_403(client, request, user_fixture, method):
    client.force_login(request.getfixturevalue(user_fixture))

    response = getattr(client, method)("/change/")

    assert response.status_code == 403


@pytest.mark.parametrize("user_fixture", ["admin", "recruiter", "hiring_manager"])
def test_role_check_allows_editors(client, request, user_fixture):
    client.force_login(request.getfixturevalue(user_fixture))

    response = client.post("/change/")

    assert response.status_code == 200
    assert response.content == b"saved"


def test_role_check_redirects_anonymous_users_to_login(client):
    response = client.post("/change/")

    assert response.status_code == 302
    assert response.url.startswith("/accounts/login/")


@pytest.mark.parametrize(
    ("user_fixture", "status"),
    [("admin", 200), ("recruiter", 200), ("hiring_manager", 403), ("interviewer", 403)],
)
def test_allowed_roles_can_be_narrowed_per_view(client, request, user_fixture, status):
    client.force_login(request.getfixturevalue(user_fixture))

    assert client.post("/recruiter-only/").status_code == status
