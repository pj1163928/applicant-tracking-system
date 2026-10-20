import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from accounts.management.commands.seed import SEED_CANDIDATES, SEED_PASSWORD, SEED_SOURCES
from accounts.roles import role_label
from candidates.models import Candidate, Source

pytestmark = pytest.mark.django_db

EXPECTED_ROLES = {
    "admin": "Admin",
    "recruiter": "Recruiter",
    "manager": "Hiring Manager",
    "interviewer": "Interviewer",
}


def snapshot():
    users = [
        (u.pk, u.username, u.password, u.first_name, u.is_superuser, role_label(u))
        for u in User.objects.order_by("username")
    ]
    candidates = list(Candidate.objects.order_by("pk").values())
    sources = list(Source.objects.order_by("pk").values())
    return users, candidates, sources


def test_seed_creates_one_user_per_role():
    call_command("seed")

    users = {u.username: u for u in User.objects.all()}
    assert {name: role_label(u) for name, u in users.items()} == EXPECTED_ROLES
    assert all(u.check_password(SEED_PASSWORD) for u in users.values())
    assert users["admin"].is_staff and users["admin"].is_superuser


def test_running_seed_twice_changes_nothing():
    call_command("seed")
    first = snapshot()

    call_command("seed")

    assert snapshot() == first


def test_seed_repairs_a_changed_seed_user():
    call_command("seed")
    user = User.objects.get(username="recruiter")
    user.set_password("something-else")
    user.groups.clear()
    user.save()

    call_command("seed")

    user.refresh_from_db()
    assert user.check_password(SEED_PASSWORD)
    assert role_label(user) == "Recruiter"


def test_seed_adds_sample_candidates_without_applications():
    call_command("seed")

    emails = set(Candidate.objects.values_list("email", flat=True))
    assert emails == {spec.email for spec in SEED_CANDIDATES}
    assert len(emails) >= 10
    assert all(email == email.lower() for email in emails)
    # Some candidates leave the optional fields blank.
    assert Candidate.objects.filter(phone="").exists()
    assert Candidate.objects.filter(notes="").exists()


def test_seed_repairs_a_changed_seed_candidate_without_duplicating_it():
    call_command("seed")
    ann = Candidate.objects.get(email="ann.lee@example.com")
    ann.last_name = "Changed"
    ann.save()

    call_command("seed")

    ann.refresh_from_db()
    assert ann.last_name == "Lee"
    assert Candidate.objects.count() == len(SEED_CANDIDATES)


def test_rerunning_seed_never_duplicates_sources_or_undoes_a_retirement():
    call_command("seed")
    indeed = Source.objects.get(name="Indeed")
    indeed.retire()  # an Admin stops using a seeded source
    monster = Source.objects.get(name="Monster")
    monster.reactivate()  # and brings back the one seed created as retired
    linkedin = Source.objects.get(name="LinkedIn Jobs")
    linkedin.name = "LINKEDIN JOBS"  # a change of capitals is the same source
    linkedin.save()

    call_command("seed")

    assert Source.objects.count() == len(SEED_SOURCES)
    assert Source.objects.get(pk=indeed.pk).is_active is False
    assert Source.objects.get(pk=monster.pk).is_active is True
    assert Source.objects.get(pk=linkedin.pk).name == "LINKEDIN JOBS"


def test_seed_adds_sources_in_every_category_with_one_retired():
    call_command("seed")

    assert set(Source.objects.values_list("name", flat=True)) == {s.name for s in SEED_SOURCES}
    assert set(Source.objects.values_list("category", flat=True)) == set(Source.Category.values)
    assert list(Source.objects.retired().values_list("name", flat=True)) == ["Monster"]


def test_seed_repairs_a_seeded_sources_category():
    call_command("seed")
    Source.objects.filter(name="Indeed").update(category=Source.Category.OTHER)

    call_command("seed")

    assert Source.objects.get(name="Indeed").category == Source.Category.JOB_BOARD
