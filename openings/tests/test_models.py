import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError

from openings.models import JobOpening
from openings.scopes import ALL, MINE

pytestmark = pytest.mark.django_db


def test_a_new_opening_is_open_and_links_to_its_detail_page(make_opening, hiring_manager):
    opening = make_opening("Backend Developer", hiring_manager)

    assert opening.status == JobOpening.Status.OPEN
    assert opening.is_open
    assert str(opening) == "Backend Developer"
    assert opening.get_absolute_url() == f"/openings/{opening.pk}/"


def test_location_is_optional_but_title_department_description_and_authority_are_required(
    hiring_manager,
):
    with pytest.raises(ValidationError) as error:
        JobOpening().full_clean()

    assert set(error.value.message_dict) == {
        "title",
        "department",
        "description",
        "designated_authority",
    }
    JobOpening(
        title="QA",
        department="Eng",
        description="Test things.",
        designated_authority=hiring_manager,
    ).full_clean()


def test_the_database_refuses_an_unknown_status(hiring_manager):
    with pytest.raises(IntegrityError):
        JobOpening.objects.bulk_create(
            [
                JobOpening(
                    title="QA",
                    department="Eng",
                    description="x",
                    status="archived",
                    designated_authority=hiring_manager,
                )
            ]
        )


def test_a_user_who_is_an_authority_cannot_be_deleted(make_opening, hiring_manager):
    make_opening("Backend Developer", hiring_manager)

    with pytest.raises(ProtectedError):
        hiring_manager.delete()


def test_mine_scope_is_the_users_own_openings_and_all_is_every_opening(
    make_opening, hiring_manager, recruiter
):
    own = make_opening("Backend Developer", hiring_manager)
    other = make_opening("Data Engineer", recruiter)

    assert list(JobOpening.objects.in_scope(MINE, hiring_manager)) == [own]
    assert set(JobOpening.objects.in_scope(ALL, hiring_manager)) == {own, other}


def test_open_first_lists_open_openings_before_closed_ones_then_by_title(
    make_opening, hiring_manager
):
    make_opening("Zoo Keeper", hiring_manager)
    make_opening("Analyst", hiring_manager, status=JobOpening.Status.CLOSED)
    make_opening("Backend Developer", hiring_manager)

    titles = [o.title for o in JobOpening.objects.open_first()]

    assert titles == ["Backend Developer", "Zoo Keeper", "Analyst"]
