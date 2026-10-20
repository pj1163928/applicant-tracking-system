import pytest
from django.db import IntegrityError, transaction

from candidates.models import Source

pytestmark = pytest.mark.django_db


def test_source_names_are_unique_regardless_of_case():
    Source.objects.create(name="LinkedIn", category=Source.Category.JOB_BOARD)

    # bulk_create skips save() and form validation, so only the database itself can refuse this.
    for clash in ["LinkedIn", "linkedin", "LINKEDIN"]:
        with pytest.raises(IntegrityError), transaction.atomic():
            Source.objects.bulk_create([Source(name=clash, category=Source.Category.OTHER)])

    assert list(Source.objects.values_list("name", flat=True)) == ["LinkedIn"]


def test_retired_sources_drop_out_of_active_choices_but_still_exist():
    indeed = Source.objects.create(name="Indeed", category=Source.Category.JOB_BOARD)
    referral = Source.objects.create(name="Employee referral", category=Source.Category.REFERRAL)

    indeed.retire()

    assert set(Source.objects.active()) == {referral}
    assert set(Source.objects.all()) == {indeed, referral}
    assert Source.objects.get(pk=indeed.pk).is_active is False

    indeed.reactivate()

    assert set(Source.objects.active()) == {indeed, referral}


def test_category_must_be_one_of_the_four_even_in_the_database():
    assert Source.Category.labels == ["Company website", "Job board", "Referral", "Other"]

    with pytest.raises(IntegrityError), transaction.atomic():
        Source.objects.bulk_create([Source(name="Carrier pigeon", category="pigeon")])


def test_sources_sort_by_name_ignoring_case_and_keep_their_capitals():
    for name in ["indeed", "Career fair", "LinkedIn Jobs"]:
        Source.objects.create(name=name, category=Source.Category.JOB_BOARD)

    assert [str(s) for s in Source.objects.all()] == ["Career fair", "indeed", "LinkedIn Jobs"]


def test_retiring_or_reactivating_twice_is_harmless():
    indeed = Source.objects.create(name="Indeed", category=Source.Category.JOB_BOARD)

    indeed.retire()
    indeed.retire()
    assert list(Source.objects.retired()) == [indeed]

    indeed.reactivate()
    indeed.reactivate()
    assert list(Source.objects.active()) == [indeed]
