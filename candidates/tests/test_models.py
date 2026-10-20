import pytest
from django.db import IntegrityError, transaction

from candidates.models import Candidate

pytestmark = pytest.mark.django_db


def test_email_is_stored_lowercase_and_unique_regardless_of_case():
    ann = Candidate.objects.create(first_name="Ann", last_name="Lee", email="Ann@X.com")
    ann.refresh_from_db()

    assert ann.email == "ann@x.com"

    # bulk_create skips save(), so only the database itself can refuse this duplicate.
    with pytest.raises(IntegrityError), transaction.atomic():
        Candidate.objects.bulk_create(
            [Candidate(first_name="Ann", last_name="Again", email="ANN@x.COM")]
        )


def test_candidate_needs_only_names_and_email_and_no_applications():
    ann = Candidate.objects.create(first_name="Ann", last_name="Lee", email="ann@x.com")

    assert ann.phone == ""
    assert ann.notes == ""
    assert str(ann) == "Ann Lee"
    assert ann.get_absolute_url() == f"/candidates/{ann.pk}/"


@pytest.fixture
def people():
    return {
        spec[0]: Candidate.objects.create(first_name=spec[0], last_name=spec[1], email=spec[2])
        for spec in [
            ("Ann", "Lee", "ann.lee@example.com"),
            ("Gus", "Lee", "gus@lee-family.net"),
            ("Bo", "Diaz", "bo.diaz@example.com"),
            ("Leena", "Park", "lp@other.org"),
        ]
    }


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("", ["Bo", "Ann", "Gus", "Leena"]),
        ("   ", ["Bo", "Ann", "Gus", "Leena"]),
        ("ann", ["Ann"]),
        ("DIAZ", ["Bo"]),
        ("lee", ["Ann", "Gus", "Leena"]),
        ("ann lee", ["Ann"]),
        ("lee ann", ["Ann"]),
        ("other.org", ["Leena"]),
        ("@example.com", ["Bo", "Ann"]),
        ("Gus@Lee-Family.net", ["Gus"]),
        ("zed", []),
    ],
)
def test_search_matches_every_word_against_name_or_email(people, query, expected):
    found = [c.first_name for c in Candidate.objects.search(query)]

    assert found == expected
