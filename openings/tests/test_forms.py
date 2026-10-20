import pytest

from openings.forms import JobOpeningCreateForm, JobOpeningForm
from openings.models import JobOpening

pytestmark = pytest.mark.django_db

INVALID_AUTHORITY = "Pick an active Admin, Recruiter or Hiring Manager."


def form_data(**overrides) -> dict:
    return {
        "title": "Backend Developer",
        "department": "Engineering",
        "location": "",
        "status": "open",
        "description": "Build our Django services.",
    } | overrides


@pytest.fixture
def everyone(admin, recruiter, hiring_manager, interviewer, no_role_user, inactive_manager):
    return locals()


def test_authority_choices_are_exactly_the_eligible_staff(everyone):
    field = JobOpeningCreateForm().fields["designated_authority"]

    choices = set(field.queryset)

    assert choices == {everyone["admin"], everyone["recruiter"], everyone["hiring_manager"]}


def test_authority_choices_are_labelled_with_name_and_role(hiring_manager):
    field = JobOpeningCreateForm().fields["designated_authority"]

    assert field.label_from_instance(hiring_manager) == "Hal Manager · Hiring Manager"


@pytest.mark.parametrize("ineligible", ["interviewer", "no_role_user", "inactive_manager"])
def test_a_hand_made_post_naming_an_ineligible_user_fails_validation(everyone, ineligible):
    # The pk never appears in the dropdown; the form must still refuse it on its own.
    form = JobOpeningCreateForm(form_data(designated_authority=everyone[ineligible].pk))

    assert not form.is_valid()
    assert form.errors["designated_authority"] == [INVALID_AUTHORITY]


def test_a_pk_that_matches_no_user_fails_validation(everyone):
    form = JobOpeningCreateForm(form_data(designated_authority=999_999))

    assert not form.is_valid()
    assert form.errors["designated_authority"] == [INVALID_AUTHORITY]


def test_the_designated_authority_is_required():
    form = JobOpeningCreateForm(form_data())

    assert not form.is_valid()
    assert form.errors["designated_authority"] == ["Every opening needs a designated authority."]


def test_an_eligible_authority_and_no_location_is_valid(recruiter):
    form = JobOpeningCreateForm(form_data(designated_authority=recruiter.pk))

    assert form.is_valid(), form.errors
    opening = form.save()
    assert opening.designated_authority == recruiter
    assert opening.location == ""


def test_the_edit_form_has_no_designated_authority_field():
    assert "designated_authority" not in JobOpeningForm().fields
    assert "designated_authority" in JobOpeningCreateForm().fields


def test_invalid_fields_are_marked_for_styling_and_screen_readers():
    form = JobOpeningCreateForm(form_data(title="", designated_authority=""))
    form.is_valid()

    title = form.fields["title"].widget.attrs
    authority = form.fields["designated_authority"].widget.attrs
    assert "input-error" in title["class"] and title["aria-invalid"] == "true"
    assert "select-error" in authority["class"] and authority["aria-invalid"] == "true"


def test_the_status_must_be_open_or_closed(recruiter):
    form = JobOpeningCreateForm(form_data(status="archived", designated_authority=recruiter.pk))

    assert not form.is_valid()
    assert "status" in form.errors
    assert JobOpening.objects.count() == 0
