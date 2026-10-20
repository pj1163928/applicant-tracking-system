import pytest
from django.urls import NoReverseMatch, reverse

from candidates.models import Source

pytestmark = pytest.mark.django_db

ALL_ROLES = ["admin", "recruiter", "hiring_manager", "interviewer", "no_role_user"]


@pytest.fixture
def indeed():
    return Source.objects.create(name="Indeed", category=Source.Category.JOB_BOARD)


@pytest.fixture
def monster():
    return Source.objects.create(
        name="Monster", category=Source.Category.JOB_BOARD, is_active=False
    )


def snapshot():
    return list(Source.objects.order_by("pk").values_list("name", "category", "is_active"))


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
def test_only_recruiters_and_admins_can_add_rename_retire_or_reactivate(
    client, request, user_fixture, allowed, indeed, monster
):
    before = snapshot()
    client.force_login(request.getfixturevalue(user_fixture))

    statuses = [
        client.get(reverse("sources:create")).status_code,
        client.post(
            reverse("sources:create"), {"name": "Career fair", "category": "other"}
        ).status_code,
        client.get(reverse("sources:update", args=[indeed.pk])).status_code,
        client.post(
            reverse("sources:update", args=[indeed.pk]), {"name": "Indeed.com"}
        ).status_code,
        client.post(reverse("sources:retire", args=[indeed.pk])).status_code,
        client.post(reverse("sources:reactivate", args=[monster.pk])).status_code,
    ]

    if allowed:
        assert statuses == [200, 302, 200, 302, 302, 302]
        assert snapshot() == [
            ("Indeed.com", "job_board", False),
            ("Monster", "job_board", True),
            ("Career fair", "other", True),
        ]
    else:
        assert statuses == [403] * 6
        assert snapshot() == before


@pytest.mark.parametrize("user_fixture", ALL_ROLES)
def test_every_role_can_view_the_sources_page(client, request, user_fixture, indeed, monster):
    client.force_login(request.getfixturevalue(user_fixture))

    response = client.get(reverse("sources:list"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Indeed" in content and "Monster" in content
    assert "Job board" in content


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
def test_actions_show_only_for_source_managers(
    client, request, user_fixture, shown, indeed, monster
):
    client.force_login(request.getfixturevalue(user_fixture))

    content = client.get(reverse("sources:list")).content.decode()

    for testid in ["source-add", "source-rename", "source-retire", "source-reactivate"]:
        assert (f'data-testid="{testid}"' in content) is shown
    assert ('data-testid="sources-read-only"' in content) is not shown


def test_active_sources_are_listed_before_retired_ones(client, interviewer, indeed, monster):
    client.force_login(interviewer)

    content = client.get(reverse("sources:list")).content.decode()

    active = content.index('data-testid="active-sources"')
    retired = content.index('data-testid="retired-sources"')
    assert active < content.index("Indeed") < retired < content.index("Monster")


def test_htmx_retire_returns_only_the_refreshed_table(client, recruiter, indeed):
    client.force_login(recruiter)

    response = client.post(reverse("sources:retire", args=[indeed.pk]), HTTP_HX_REQUEST="true")

    content = response.content.decode()
    assert response.status_code == 200
    assert "<html" not in content
    assert 'id="source-table"' in content
    assert "Retired Indeed." in content
    assert 'data-testid="no-active-sources"' in content
    assert content.index('data-testid="retired-sources"') < content.index(
        'data-testid="source-row"'
    )
    assert Source.objects.retired().get() == indeed


def test_htmx_reactivate_moves_the_source_back_to_active(client, admin, monster):
    client.force_login(admin)

    response = client.post(reverse("sources:reactivate", args=[monster.pk]), HTTP_HX_REQUEST="true")

    content = response.content.decode()
    assert "Reactivated Monster." in content
    assert 'data-testid="no-retired-sources"' in content
    assert Source.objects.active().get() == monster


def test_retire_without_htmx_redirects_with_a_message(client, recruiter, indeed):
    client.force_login(recruiter)

    response = client.post(reverse("sources:retire", args=[indeed.pk]), follow=True)

    assert response.redirect_chain == [(reverse("sources:list"), 302)]
    assert "Retired Indeed." in response.content.decode()


def test_retire_and_reactivate_refuse_get(client, recruiter, indeed):
    client.force_login(recruiter)

    assert client.get(reverse("sources:retire", args=[indeed.pk])).status_code == 405
    assert client.get(reverse("sources:reactivate", args=[indeed.pk])).status_code == 405
    assert Source.objects.get(pk=indeed.pk).is_active is True


def test_adding_a_source_redirects_to_the_list_with_a_message(client, recruiter):
    client.force_login(recruiter)

    response = client.post(
        reverse("sources:create"), {"name": "Career fair", "category": "other"}, follow=True
    )

    assert response.redirect_chain == [(reverse("sources:list"), 302)]
    assert "Added Career fair." in response.content.decode()
    assert Source.objects.get().category == Source.Category.OTHER


def test_duplicate_name_in_another_case_shows_a_clear_error(client, recruiter, indeed):
    client.force_login(recruiter)

    response = client.post(reverse("sources:create"), {"name": "INDEED", "category": "other"})

    content = response.content.decode()
    assert response.status_code == 200
    assert 'data-testid="error-name"' in content
    assert "A source with this name already exists." in content
    assert Source.objects.count() == 1


def test_failed_rename_keeps_the_saved_name_in_the_heading(client, recruiter, indeed):
    Source.objects.create(name="Career fair", category=Source.Category.OTHER)
    client.force_login(recruiter)

    response = client.post(reverse("sources:update", args=[indeed.pk]), {"name": "career FAIR"})

    content = response.content.decode()
    assert "Rename Indeed" in content
    assert "A source with this name already exists." in content
    assert 'data-testid="source-category"' in content
    assert Source.objects.get(pk=indeed.pk).name == "Indeed"


def test_rename_redirects_to_the_list_with_a_message(client, admin, indeed):
    client.force_login(admin)

    response = client.post(
        reverse("sources:update", args=[indeed.pk]), {"name": "Indeed.com"}, follow=True
    )

    assert response.redirect_chain == [(reverse("sources:list"), 302)]
    assert "Renamed the source to Indeed.com." in response.content.decode()


def test_no_url_or_admin_action_deletes_a_source(client, admin, indeed):
    client.force_login(admin)

    with pytest.raises(NoReverseMatch):
        reverse("sources:delete", args=[indeed.pk])
    assert client.post(f"/sources/{indeed.pk}/delete/").status_code == 404
    assert (
        client.post(reverse("admin:candidates_source_delete", args=[indeed.pk])).status_code == 403
    )
    changelist = client.get(reverse("admin:candidates_source_changelist")).content.decode()
    assert "delete_selected" not in changelist
    assert Source.objects.filter(pk=indeed.pk).exists()


@pytest.mark.parametrize(
    ("url_name", "needs_pk"),
    [
        ("sources:list", False),
        ("sources:create", False),
        ("sources:update", True),
        ("sources:retire", True),
        ("sources:reactivate", True),
    ],
)
def test_anonymous_users_are_sent_to_login(client, indeed, url_name, needs_pk):
    response = client.post(reverse(url_name, args=[indeed.pk] if needs_pk else []))

    assert response.status_code == 302
    assert response.url.startswith(reverse("accounts:login"))
    assert Source.objects.get(pk=indeed.pk).is_active is True


def test_missing_source_is_404(client, recruiter):
    client.force_login(recruiter)

    assert client.get(reverse("sources:update", args=[999])).status_code == 404
    assert client.post(reverse("sources:retire", args=[999])).status_code == 404


def test_nav_has_a_sources_link_marked_current_on_the_sources_page(client, interviewer):
    client.force_login(interviewer)

    content = client.get(reverse("sources:list")).content.decode()

    assert f'href="{reverse("sources:list")}"' in content
    # Each link appears in both menus; only Sources is current.
    assert content.count('aria-current="page"') == 2
