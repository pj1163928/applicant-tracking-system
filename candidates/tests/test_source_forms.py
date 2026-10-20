import pytest

from candidates.forms import SourceForm, SourceRenameForm
from candidates.models import Source

pytestmark = pytest.mark.django_db


@pytest.fixture
def indeed():
    return Source.objects.create(name="Indeed", category=Source.Category.JOB_BOARD)


@pytest.mark.parametrize("name", ["Indeed", "indeed", "INDEED", "  indeed  "])
def test_add_form_reports_a_duplicate_name_in_any_case_on_the_name_field(indeed, name):
    form = SourceForm(data={"name": name, "category": Source.Category.OTHER})

    assert not form.is_valid()
    assert form.errors == {"name": ["A source with this name already exists."]}
    assert 'aria-invalid="true"' in str(form["name"])


def test_add_form_saves_the_name_as_typed_without_outer_spaces():
    source = SourceForm(data={"name": "  LinkedIn Jobs ", "category": "job_board"}).save()

    assert source.name == "LinkedIn Jobs"
    assert source.category == Source.Category.JOB_BOARD
    assert source.is_active is True


@pytest.mark.parametrize("category", ["", "pigeon"])
def test_add_form_needs_one_of_the_four_categories(category):
    form = SourceForm(data={"name": "Carrier pigeon", "category": category})

    assert not form.is_valid()
    assert list(form.errors) == ["category"]
    assert "select-error" in str(form["category"])


def test_add_form_offers_exactly_the_four_categories():
    choices = [label for value, label in SourceForm().fields["category"].choices if value]

    assert choices == ["Company website", "Job board", "Referral", "Other"]


def test_rename_form_changes_only_the_name(indeed):
    form = SourceRenameForm(data={"name": "Indeed.com", "category": "other"}, instance=indeed)

    assert list(form.fields) == ["name"]
    assert form.is_valid(), form.errors
    form.save()
    indeed.refresh_from_db()
    assert (indeed.name, indeed.category) == ("Indeed.com", Source.Category.JOB_BOARD)


def test_rename_can_change_only_the_capitals_of_its_own_name(indeed):
    form = SourceRenameForm(data={"name": "INDEED"}, instance=indeed)

    assert form.is_valid(), form.errors


def test_rename_to_another_sources_name_is_refused(indeed):
    fair = Source.objects.create(name="Career fair", category=Source.Category.OTHER)

    form = SourceRenameForm(data={"name": "indeed"}, instance=fair)

    assert form.errors == {"name": ["A source with this name already exists."]}


def test_name_is_required():
    assert list(SourceForm(data={"name": "", "category": "other"}).errors) == ["name"]
