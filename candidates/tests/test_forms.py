import pytest

from candidates.forms import CandidateForm
from candidates.models import Candidate

pytestmark = pytest.mark.django_db


def form(**overrides):
    data = {"first_name": "Ann", "last_name": "Lee", "email": "ann@x.com", **overrides}
    return CandidateForm(data=data)


def test_form_lowercases_the_email():
    candidate = form(email="  Ann@X.COM ").save()

    assert candidate.email == "ann@x.com"


@pytest.mark.parametrize("email", ["ann@x.com", "Ann@X.com", "ANN@X.COM"])
def test_form_reports_a_duplicate_email_in_any_case_on_the_email_field(email):
    Candidate.objects.create(first_name="Ann", last_name="Lee", email="ann@x.com")

    duplicate = form(first_name="Annie", email=email)

    assert not duplicate.is_valid()
    assert duplicate.errors == {"email": ["A candidate with this email already exists."]}


def test_editing_a_candidate_keeps_their_own_email_valid():
    ann = Candidate.objects.create(first_name="Ann", last_name="Lee", email="ann@x.com")

    edit = CandidateForm(
        data={"first_name": "Ann", "last_name": "Lee-Park", "email": "ANN@x.com"}, instance=ann
    )

    assert edit.is_valid(), edit.errors
    assert edit.save().email == "ann@x.com"


@pytest.mark.parametrize("field", ["first_name", "last_name", "email"])
def test_names_and_email_are_required(field):
    blank = form(**{field: ""})

    assert not blank.is_valid()
    assert list(blank.errors) == [field]


def test_email_must_be_a_valid_address():
    assert list(form(email="not-an-email").errors) == ["email"]


def test_phone_and_notes_are_optional():
    assert form(phone="", notes="").is_valid()


def test_invalid_inputs_are_marked_for_styling_and_screen_readers():
    Candidate.objects.create(first_name="Ann", last_name="Lee", email="ann@x.com")

    bound = form(first_name="", email="ANN@x.com")
    bound.is_valid()

    assert 'aria-invalid="true"' in str(bound["email"])
    assert "input-error" in str(bound["email"])
    assert "input-error" in str(bound["first_name"])
    assert "input-error" not in str(bound["last_name"])
