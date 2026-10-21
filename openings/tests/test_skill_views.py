import html

import pytest
from django.urls import reverse

from openings.models import Skill

pytestmark = pytest.mark.django_db

# On skilled_opening, whose designated authority is the Recruiter Riley Chen.
MANAGERS = ["admin", "hiring_manager", "authority"]
READ_ONLY = ["recruiter", "interviewer", "no_role_user"]


def page(response) -> str:
    return html.unescape(response.content.decode())


def attach_url(opening) -> str:
    return reverse("openings:skill_attach", args=[opening.pk])


def detach_url(opening, skill) -> str:
    return reverse("openings:skill_detach", args=[opening.pk, skill.pk])


def skill_names(opening) -> list[str]:
    return list(opening.skills.values_list("name", flat=True))


@pytest.fixture
def python(skilled_opening):
    """Python, already listed on skilled_opening."""
    skill = Skill.objects.create(name="Python")
    skilled_opening.skills.add(skill)
    return skill


@pytest.mark.parametrize("user_fixture", MANAGERS)
def test_managers_add_create_and_remove_skills_through_htmx(
    client, request, user_fixture, skilled_opening, python
):
    Skill.objects.create(name="Customer service")
    client.force_login(request.getfixturevalue(user_fixture))

    reused = client.post(
        attach_url(skilled_opening), {"name": "customer SERVICE"}, HTTP_HX_REQUEST="true"
    )
    created = client.post(attach_url(skilled_opening), {"name": "Zendesk"}, HTTP_HX_REQUEST="true")
    removed = client.post(detach_url(skilled_opening, python), HTTP_HX_REQUEST="true")

    assert [r.status_code for r in (reused, created, removed)] == [200, 200, 200]
    for response in (reused, created, removed):
        assert "<html" not in response.content.decode()  # only the Skills section
        assert 'id="opening-skills"' in response.content.decode()
        assert "HX-Request" in response["Vary"]
    assert "Added Customer service to Support Specialist." in page(reused)
    assert "Added Zendesk to Support Specialist." in page(created)
    assert "Removed Python from Support Specialist." in page(removed)
    assert skill_names(skilled_opening) == ["Customer service", "Zendesk"]
    assert Skill.objects.count() == 3  # Python kept, Customer service reused, Zendesk new


@pytest.mark.parametrize("user_fixture", READ_ONLY)
def test_read_only_roles_are_refused_when_posting_directly(
    client, request, user_fixture, skilled_opening, python
):
    client.force_login(request.getfixturevalue(user_fixture))

    statuses = [
        client.post(attach_url(skilled_opening), {"name": "Django"}).status_code,
        client.post(
            attach_url(skilled_opening), {"name": "Django"}, HTTP_HX_REQUEST="true"
        ).status_code,
        client.post(detach_url(skilled_opening, python)).status_code,
    ]

    assert statuses == [403, 403, 403]
    assert skill_names(skilled_opening) == ["Python"]
    assert not Skill.objects.filter(name="Django").exists()


def test_the_authority_is_refused_on_someone_elses_opening(
    client, authority, make_opening, hiring_manager
):
    someone_elses = make_opening("Backend Developer", hiring_manager)
    client.force_login(authority)

    response = client.post(attach_url(someone_elses), {"name": "Python"})

    assert response.status_code == 403
    assert skill_names(someone_elses) == []


@pytest.mark.parametrize(
    ("user_fixture", "can_edit"),
    [(name, True) for name in MANAGERS] + [(name, False) for name in READ_ONLY],
)
def test_the_section_shows_skills_to_everyone_and_controls_only_to_managers(
    client, request, user_fixture, can_edit, skilled_opening, python
):
    client.force_login(request.getfixturevalue(user_fixture))

    content = client.get(skilled_opening.get_absolute_url()).content.decode()

    assert 'data-testid="skills-section"' in content
    assert content.count('data-testid="skill"') == 1
    assert ('data-testid="skill-add-form"' in content) is can_edit
    assert ('data-testid="skill-detach"' in content) is can_edit
    assert ('data-testid="skills-read-only"' in content) is not can_edit


def test_a_retired_skill_stays_on_the_opening_marked_retired_but_is_not_suggested(
    client, hiring_manager, skilled_opening, python
):
    jquery = Skill.objects.create(name="jQuery")
    skilled_opening.skills.add(jquery)
    jquery.retire()
    Skill.objects.create(name="Django")
    Skill.objects.create(name="COBOL", is_active=False)
    client.force_login(hiring_manager)

    response = client.get(skilled_opening.get_absolute_url())

    assert [s.name for s in response.context["skills"]] == ["jQuery", "Python"]
    assert response.content.decode().count('data-testid="skill-retired"') == 1
    # Suggestions are active skills the opening doesn't list yet.
    assert [s.name for s in response.context["skill_suggestions"]] == ["Django"]


def test_adding_a_retired_skill_is_refused_with_a_message_under_the_box(
    client, hiring_manager, skilled_opening
):
    Skill.objects.create(name="jQuery", is_active=False)
    client.force_login(hiring_manager)

    response = client.post(attach_url(skilled_opening), {"name": "jquery"}, HTTP_HX_REQUEST="true")

    assert response.status_code == 200
    assert 'data-testid="error-skill-name"' in response.content.decode()
    assert "jQuery is retired, so it can't be added to openings." in page(response)
    assert 'aria-invalid="true"' in response.content.decode()
    assert skill_names(skilled_opening) == []


@pytest.mark.parametrize(
    ("typed", "message"),
    [
        ("", "Type a skill name."),
        ("   ", "Type a skill name."),
        ("python", "Support Specialist already lists Python."),
        ("x" * 61, "Ensure this value has at most 60 characters (it has 61)."),
    ],
)
def test_blank_duplicate_or_overlong_names_show_an_error_and_change_nothing(
    client, hiring_manager, skilled_opening, python, typed, message
):
    client.force_login(hiring_manager)

    response = client.post(attach_url(skilled_opening), {"name": typed}, HTTP_HX_REQUEST="true")

    assert message in page(response)
    assert skill_names(skilled_opening) == ["Python"]
    assert Skill.objects.count() == 1


def test_without_htmx_changes_redirect_back_with_a_message(client, hiring_manager, skilled_opening):
    client.force_login(hiring_manager)

    added = client.post(attach_url(skilled_opening), {"name": "Python"}, follow=True)
    refused = client.post(attach_url(skilled_opening), {"name": "Python"}, follow=True)

    assert added.redirect_chain == [(skilled_opening.get_absolute_url(), 302)]
    assert "Added Python to Support Specialist." in page(added)
    assert "Support Specialist already lists Python." in page(refused)


def test_removing_a_skill_the_opening_doesnt_list_says_so(client, hiring_manager, skilled_opening):
    other = Skill.objects.create(name="Figma")
    client.force_login(hiring_manager)

    response = client.post(detach_url(skilled_opening, other), HTTP_HX_REQUEST="true")

    assert "Support Specialist doesn't list Figma." in page(response)


def test_the_skill_endpoints_take_post_only(client, hiring_manager, skilled_opening, python):
    client.force_login(hiring_manager)

    assert client.get(attach_url(skilled_opening)).status_code == 405
    assert client.get(detach_url(skilled_opening, python)).status_code == 405


# The skills page: retiring and reactivating.


def retire_url(skill) -> str:
    return reverse("skills:retire", args=[skill.pk])


def reactivate_url(skill) -> str:
    return reverse("skills:reactivate", args=[skill.pk])


@pytest.mark.parametrize("user_fixture", MANAGERS + READ_ONLY)
def test_everyone_can_view_the_skills_page_with_usage_counts(
    client, request, user_fixture, skilled_opening, python, make_opening, hiring_manager
):
    make_opening("Backend Developer", hiring_manager).skills.add(python)
    Skill.objects.create(name="COBOL", is_active=False)
    client.force_login(request.getfixturevalue(user_fixture))

    response = client.get(reverse("skills:list"))

    assert response.status_code == 200
    assert [s.name for s in response.context["active_skills"]] == ["Python"]
    assert [s.name for s in response.context["retired_skills"]] == ["COBOL"]
    assert "Listed on 2 openings" in page(response)
    assert "Not on any opening" in page(response)


@pytest.mark.parametrize(
    ("user_fixture", "allowed"),
    [
        ("admin", True),
        ("hiring_manager", True),
        ("authority", False),  # an opening's authority never retires skills
        ("recruiter", False),
        ("interviewer", False),
        ("no_role_user", False),
    ],
)
def test_only_admins_and_hiring_managers_can_retire_or_reactivate_skills(
    client, request, user_fixture, allowed, python
):
    client.force_login(request.getfixturevalue(user_fixture))

    retire = client.post(retire_url(python))
    python.refresh_from_db()
    retired = not python.is_active
    reactivate = client.post(reactivate_url(python))
    python.refresh_from_db()

    if allowed:
        assert [retire.status_code, reactivate.status_code] == [302, 302]
        assert retired and python.is_active
    else:
        assert [retire.status_code, reactivate.status_code] == [403, 403]
        assert not retired and python.is_active


@pytest.mark.parametrize(
    ("user_fixture", "sees_actions"),
    [("admin", True), ("hiring_manager", True), ("authority", False), ("interviewer", False)],
)
def test_retire_buttons_show_only_for_those_who_can_use_them(
    client, request, user_fixture, sees_actions, python
):
    client.force_login(request.getfixturevalue(user_fixture))

    content = client.get(reverse("skills:list")).content.decode()

    assert ('data-testid="skill-retire"' in content) is sees_actions
    assert ('data-testid="skills-page-read-only"' in content) is not sees_actions


def test_htmx_retire_returns_the_table_and_the_skill_stays_on_its_opening(
    client, hiring_manager, skilled_opening, python
):
    client.force_login(hiring_manager)

    response = client.post(retire_url(python), HTTP_HX_REQUEST="true")

    content = page(response)
    assert "<html" not in content
    assert 'id="skill-table"' in content
    assert "Retired Python. Openings that list it keep it; others can't add it." in content
    assert skill_names(skilled_opening) == ["Python"]


def test_no_skill_can_be_deleted_in_the_django_admin(client, admin, python):
    client.force_login(admin)

    response = client.get(reverse("admin:openings_skill_change", args=[python.pk]))

    assert response.status_code == 200
    assert response.context["has_delete_permission"] is False


def test_anonymous_users_are_sent_to_login(client, skilled_opening, python):
    for method, url in [
        ("get", reverse("skills:list")),
        ("post", attach_url(skilled_opening)),
        ("post", detach_url(skilled_opening, python)),
        ("post", retire_url(python)),
    ]:
        response = getattr(client, method)(url)
        assert response.status_code == 302
        assert response["Location"].startswith("/accounts/login/")


def test_the_nav_links_to_skills_and_marks_it_current(client, interviewer):
    client.force_login(interviewer)

    content = client.get(reverse("skills:list")).content.decode()

    assert f'href="{reverse("skills:list")}" class="menu-active' in content
