import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from openings.models import Skill
from openings.services import (
    ALREADY_LISTED,
    BLANK_SKILL,
    RETIRED_SKILL,
    SKILL_TOO_LONG,
    attach_skill,
    detach_skill,
)

pytestmark = pytest.mark.django_db


def skill_names(opening) -> list[str]:
    return list(opening.skills.values_list("name", flat=True))


@pytest.mark.parametrize("typed", ["python", "PYTHON", "  Python  "])
def test_adding_a_skill_by_name_reuses_the_existing_skill_regardless_of_case(
    typed, make_opening, hiring_manager
):
    python = Skill.objects.create(name="Python")
    opening = make_opening("Backend Developer", hiring_manager)

    attached = attach_skill(opening, typed, by=hiring_manager)

    assert attached == python
    assert list(opening.skills.all()) == [python]
    assert list(Skill.objects.values_list("name", flat=True)) == ["Python"]  # no near-duplicate


def test_adding_an_unknown_skill_creates_it_with_the_typed_capitals_and_tidy_spaces(
    make_opening, hiring_manager
):
    opening = make_opening("QA Analyst", hiring_manager)

    skill = attach_skill(opening, "  Test   automation ", by=hiring_manager)

    assert skill.name == "Test automation"
    assert skill.is_active
    assert list(opening.skills.all()) == [skill]


def test_the_same_skill_can_be_listed_on_many_openings(make_opening, hiring_manager):
    backend = make_opening("Backend Developer", hiring_manager)
    data = make_opening("Data Engineer", hiring_manager, department="Data")

    first = attach_skill(backend, "Python", by=hiring_manager)
    second = attach_skill(data, "python", by=hiring_manager)

    assert first == second
    assert set(first.openings.all()) == {backend, data}
    assert Skill.objects.count() == 1


def test_a_retired_skill_cannot_be_added_and_nothing_is_written(make_opening, hiring_manager):
    jquery = Skill.objects.create(name="jQuery", is_active=False)
    opening = make_opening("Backend Developer", hiring_manager)

    with pytest.raises(ValidationError) as error:
        attach_skill(opening, "JQUERY", by=hiring_manager)

    assert error.value.code == RETIRED_SKILL
    assert error.value.messages == ["jQuery is retired, so it can't be added to openings."]
    assert skill_names(opening) == []
    assert list(Skill.objects.all()) == [jquery]


def test_a_skill_already_listed_is_refused(make_opening, hiring_manager):
    opening = make_opening("Backend Developer", hiring_manager)
    attach_skill(opening, "Python", by=hiring_manager)

    with pytest.raises(ValidationError) as error:
        attach_skill(opening, "python", by=hiring_manager)

    assert error.value.code == ALREADY_LISTED
    assert error.value.messages == ["Backend Developer already lists Python."]
    assert skill_names(opening) == ["Python"]


@pytest.mark.parametrize(
    ("typed", "code"), [("", BLANK_SKILL), ("   ", BLANK_SKILL), ("x" * 61, SKILL_TOO_LONG)]
)
def test_blank_or_overlong_names_are_refused(typed, code, make_opening, hiring_manager):
    opening = make_opening("Backend Developer", hiring_manager)

    with pytest.raises(ValidationError) as error:
        attach_skill(opening, typed, by=hiring_manager)

    assert error.value.code == code
    assert Skill.objects.count() == 0


@pytest.mark.parametrize("user_fixture", ["recruiter", "interviewer", "no_role_user"])
def test_only_those_who_manage_the_openings_skills_can_change_them(
    request, user_fixture, skilled_opening
):
    user = request.getfixturevalue(user_fixture)
    python = Skill.objects.create(name="Python")
    skilled_opening.skills.add(python)

    with pytest.raises(PermissionDenied) as error:
        attach_skill(skilled_opening, "Django", by=user)
    with pytest.raises(PermissionDenied):
        detach_skill(skilled_opening, python, by=user)

    assert str(error.value) == (
        "Only Admins, Hiring Managers or Riley Chen, this opening's designated authority, "
        "can change its skills."
    )
    assert skill_names(skilled_opening) == ["Python"]
    assert Skill.objects.count() == 1  # Django was not created either


def test_the_authority_changes_their_own_openings_skills_only(
    authority, skilled_opening, make_opening, hiring_manager
):
    someone_elses = make_opening("Backend Developer", hiring_manager)

    attach_skill(skilled_opening, "Customer service", by=authority)

    with pytest.raises(PermissionDenied):
        attach_skill(someone_elses, "Python", by=authority)
    assert skill_names(skilled_opening) == ["Customer service"]
    assert skill_names(someone_elses) == []


def test_detaching_removes_the_skill_from_that_opening_only(make_opening, hiring_manager):
    backend = make_opening("Backend Developer", hiring_manager)
    data = make_opening("Data Engineer", hiring_manager, department="Data")
    python = attach_skill(backend, "Python", by=hiring_manager)
    attach_skill(data, "Python", by=hiring_manager)

    assert detach_skill(backend, python, by=hiring_manager) is True
    assert detach_skill(backend, python, by=hiring_manager) is False  # already gone

    assert skill_names(backend) == []
    assert skill_names(data) == ["Python"]
    assert Skill.objects.filter(pk=python.pk).exists()  # the skill itself is kept


def test_a_retired_skill_can_still_be_detached(make_opening, hiring_manager):
    opening = make_opening("Backend Developer", hiring_manager)
    jquery = attach_skill(opening, "jQuery", by=hiring_manager)
    jquery.retire()

    assert detach_skill(opening, jquery, by=hiring_manager) is True
    assert skill_names(opening) == []
