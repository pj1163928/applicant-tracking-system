import pytest

from applications.forms import ApplicationForm, ApplicationSourceForm
from applications.models import Application
from candidates.models import Source

pytestmark = pytest.mark.django_db


def test_a_second_application_for_the_same_opening_gets_a_friendly_form_error(
    apply, ann, backend, indeed, linkedin
):
    apply(ann, backend, indeed)

    form = ApplicationForm(data={"candidate": ann.pk, "opening": backend.pk, "source": linkedin.pk})

    assert not form.is_valid()
    assert form.errors == {"opening": ["Ann Lee has already applied for Backend Developer."]}
    assert Application.objects.count() == 1


def test_the_opening_choices_are_only_open_openings(backend, qa, closed_opening):
    form = ApplicationForm()

    assert set(form.fields["opening"].queryset) == {backend, qa}


def test_a_hand_made_post_naming_a_closed_opening_fails_validation(ann, closed_opening, indeed):
    form = ApplicationForm(
        data={"candidate": ann.pk, "opening": closed_opening.pk, "source": indeed.pk}
    )

    assert not form.is_valid()
    assert form.errors == {
        "opening": ["Pick an open opening. Closed openings don't take new applications."]
    }


def test_new_applications_can_only_pick_active_sources(indeed, linkedin, monster):
    form = ApplicationForm()

    assert set(form.fields["source"].queryset) == {indeed, linkedin}


def test_a_hand_made_post_naming_a_retired_source_fails_validation(ann, backend, monster):
    form = ApplicationForm(data={"candidate": ann.pk, "opening": backend.pk, "source": monster.pk})

    assert not form.is_valid()
    assert form.errors == {
        "source": ["Pick an active source. Retired sources can't be used for new applications."]
    }


def test_every_field_but_referred_by_is_required():
    form = ApplicationForm(data={})

    assert not form.is_valid()
    assert form.errors == {
        "candidate": ["Pick the candidate who applied."],
        "opening": ["Pick the opening they applied for."],
        "source": ["Pick where the application came from."],
    }


@pytest.mark.parametrize(("source_fixture", "shows"), [("referral", True), ("indeed", False)])
def test_referred_by_shows_only_for_a_referral_source(request, source_fixture, shows):
    source = request.getfixturevalue(source_fixture)

    assert ApplicationForm(initial={"source": source.pk}).shows_referred_by is shows
    assert ApplicationForm(data={"source": source.pk}).shows_referred_by is shows


def test_referred_by_is_hidden_until_a_source_is_picked():
    assert ApplicationForm().shows_referred_by is False
    assert ApplicationForm(data={"source": "not-a-pk"}).shows_referred_by is False


def test_the_form_drops_referred_by_for_a_non_referral_source(ann, backend, indeed):
    form = ApplicationForm(
        data={
            "candidate": ann.pk,
            "opening": backend.pk,
            "source": indeed.pk,
            "referred_by": "Dana Lee",
        }
    )

    assert form.is_valid()
    assert form.cleaned_data["referred_by"] == ""


def test_retired_sources_are_labelled_and_labels_name_the_category(monster, referral):
    field = ApplicationForm().fields["source"]

    assert field.label_from_instance(referral) == "Employee referral · Referral"
    assert field.label_from_instance(monster) == "Monster · Job board (retired)"


def test_an_old_applications_form_still_shows_its_retired_source(
    apply, ann, backend, monster, indeed, linkedin
):
    application = apply(ann, backend, indeed)
    Application.objects.filter(pk=application.pk).update(source=monster)  # applied before retiring
    application.refresh_from_db()

    form = ApplicationSourceForm(instance=application)

    assert set(form.fields["source"].queryset) == {indeed, linkedin, monster}
    assert form["source"].value() == monster.pk
    assert "Monster · Job board (retired)" in str(form["source"])


def test_saving_an_old_application_unchanged_keeps_its_retired_source(
    apply, ann, backend, monster, indeed
):
    application = apply(ann, backend, indeed)
    Application.objects.filter(pk=application.pk).update(source=monster)
    application.refresh_from_db()

    form = ApplicationSourceForm(data={"source": monster.pk}, instance=application)

    assert form.is_valid()
    form.save()
    application.refresh_from_db()
    assert application.source == monster


def test_an_old_application_cannot_switch_to_a_different_retired_source(
    apply, ann, backend, monster, indeed
):
    other_retired = Source.objects.create(
        name="Dice", category=Source.Category.JOB_BOARD, is_active=False
    )
    application = apply(ann, backend, indeed)
    form = ApplicationSourceForm(data={"source": other_retired.pk}, instance=application)

    assert not form.is_valid()
    assert form.errors == {
        "source": ["Pick an active source, or keep this application's own source."]
    }
    assert other_retired not in form.fields["source"].queryset
    assert monster not in form.fields["source"].queryset


def test_switching_an_old_application_away_from_referral_clears_referred_by(
    apply, ann, backend, referral, indeed
):
    application = apply(ann, backend, referral, referred_by="Dana Lee")

    form = ApplicationSourceForm(
        data={"source": indeed.pk, "referred_by": "Dana Lee"}, instance=application
    )

    assert form.is_valid()
    form.save()
    application.refresh_from_db()
    assert (application.source, application.referred_by) == (indeed, "")
