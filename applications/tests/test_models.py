import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from applications.models import Application, StageChange
from applications.stages import Stage
from candidates.models import Source

pytestmark = pytest.mark.django_db


def test_the_database_refuses_a_second_application_for_the_same_opening(
    apply, ann, backend, indeed
):
    apply(ann, backend, indeed)

    # bulk_create skips save() and form validation: only the database constraint is left.
    with pytest.raises(IntegrityError), transaction.atomic():
        Application.objects.bulk_create(
            [Application(candidate=ann, opening=backend, source=indeed)]
        )
    assert Application.objects.count() == 1


def test_one_candidate_can_apply_for_many_openings_and_one_opening_takes_many_candidates(
    apply, ann, ben, backend, qa, indeed
):
    apply(ann, backend, indeed)
    apply(ann, qa, indeed)
    apply(ben, backend, indeed)

    assert ann.applications.count() == 2
    assert backend.applications.count() == 2


def test_the_database_refuses_a_stage_outside_the_eight_stages(apply, ann, backend, indeed):
    application = apply(ann, backend, indeed)

    with pytest.raises(IntegrityError), transaction.atomic():
        Application.objects.filter(pk=application.pk).update(stage="lunch")


def test_the_database_allows_only_one_initial_history_row_per_application(
    apply, ann, backend, indeed, recruiter
):
    application = apply(ann, backend, indeed)

    with pytest.raises(IntegrityError), transaction.atomic():
        StageChange.objects.create(
            application=application, from_stage="", to_stage=Stage.APPLIED, changed_by=recruiter
        )
    assert application.stage_changes.count() == 1


def test_the_database_refuses_a_history_row_that_does_not_change_the_stage(
    apply, ann, backend, indeed, recruiter
):
    application = apply(ann, backend, indeed)

    with pytest.raises(IntegrityError), transaction.atomic():
        StageChange.objects.create(
            application=application,
            from_stage=Stage.APPLIED,
            to_stage=Stage.APPLIED,
            changed_by=recruiter,
        )


def test_sources_openings_and_staff_with_applications_cannot_be_deleted(
    apply, ann, backend, indeed, recruiter
):
    apply(ann, backend, indeed)

    for record in (indeed, backend, recruiter):
        with pytest.raises(ProtectedError), transaction.atomic():
            record.delete()
    assert Application.objects.count() == 1


def test_deleting_a_candidate_removes_their_applications_and_history(apply, ann, backend, indeed):
    apply(ann, backend, indeed)

    ann.delete()

    assert Application.objects.count() == 0
    assert StageChange.objects.count() == 0


def test_saving_from_code_clears_referred_by_when_the_source_is_not_a_referral(
    apply, ann, backend, referral, indeed
):
    application = apply(ann, backend, referral, referred_by="Dana Lee")
    assert application.referred_by == "Dana Lee"

    application.source = indeed
    application.save(update_fields=["source"])

    application.refresh_from_db()
    assert application.referred_by == ""


def test_referred_by_is_kept_and_trimmed_for_a_referral_source(apply, ann, backend, referral):
    application = apply(ann, backend, referral, referred_by="  Dana Lee  ")

    application.refresh_from_db()
    assert application.referred_by == "Dana Lee"


def test_referred_by_is_never_stored_for_a_new_non_referral_application(
    apply, ann, backend, indeed
):
    application = apply(ann, backend, indeed, referred_by="Dana Lee")

    application.refresh_from_db()
    assert application.referred_by == ""


@pytest.mark.parametrize(
    ("category", "shows"),
    [(value, value == Source.Category.REFERRAL) for value in Source.Category.values],
)
def test_only_referral_sources_show_referred_by(apply, ann, backend, category, shows):
    source = Source.objects.create(name=f"Source {category}", category=category)

    assert apply(ann, backend, source).shows_referred_by is shows
