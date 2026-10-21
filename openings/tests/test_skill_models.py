import pytest
from django.db import IntegrityError
from django.db.models import ProtectedError

from openings.models import Skill

pytestmark = pytest.mark.django_db


def test_the_database_refuses_a_skill_name_that_differs_only_in_capitals():
    Skill.objects.create(name="Python")

    with pytest.raises(IntegrityError):
        Skill.objects.bulk_create([Skill(name="PYTHON")])  # skips save() and form checks


def test_a_skill_keeps_the_capitals_it_was_given():
    Skill.objects.create(name="JavaScript")

    assert Skill.objects.named("javascript").get().name == "JavaScript"


def test_retiring_and_reactivating_keeps_the_skill(make_opening, hiring_manager):
    figma = Skill.objects.create(name="Figma")
    opening = make_opening("Product Designer", hiring_manager)
    opening.skills.add(figma)

    figma.retire()

    assert list(Skill.objects.active()) == []
    assert list(Skill.objects.retired()) == [figma]
    assert list(opening.skills.all()) == [figma]  # still listed where it was

    figma.reactivate()

    assert list(Skill.objects.active()) == [figma]


def test_a_skill_listed_on_an_opening_cannot_be_deleted(make_opening, hiring_manager):
    sql = Skill.objects.create(name="SQL")
    make_opening("Data Engineer", hiring_manager).skills.add(sql)

    with pytest.raises(ProtectedError):
        sql.delete()
