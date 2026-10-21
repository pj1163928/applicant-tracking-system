import pytest
from django.contrib.auth.models import Group, User
from django.core.management import call_command

from accounts.management.commands.seed import (
    SEED_APPLICATIONS,
    SEED_CANDIDATES,
    SEED_MOVES,
    SEED_OPENING_SKILLS,
    SEED_OPENINGS,
    SEED_PASSWORD,
    SEED_SKILLS,
    SEED_SOURCES,
    seed_moves,
)
from accounts.roles import role_label
from applications.models import Application, StageChange
from applications.services import move_application, prefill_source
from applications.stages import Stage, can_move, requires_note
from candidates.models import Candidate, Source
from openings.models import JobOpening, OpeningSkill, Skill

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
    openings = list(JobOpening.objects.order_by("pk").values())
    applications = list(Application.objects.order_by("pk").values())
    stage_changes = list(StageChange.objects.order_by("pk").values())
    skills = list(Skill.objects.order_by("pk").values())
    opening_skills = list(OpeningSkill.objects.order_by("pk").values())
    return users, candidates, sources, openings, applications, stage_changes, skills, opening_skills


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


def test_seed_adds_sample_candidates():
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


def test_seed_adds_open_and_closed_openings_with_different_authorities():
    call_command("seed")

    openings = JobOpening.objects.select_related("designated_authority")
    assert openings.count() == len(SEED_OPENINGS)
    assert set(openings.values_list("status", flat=True)) == {"open", "closed"}
    authorities = {o.designated_authority.username for o in openings}
    assert authorities == {"manager", "recruiter", "admin"}
    assert openings.filter(location="").exists()
    # The Hiring Manager's "My openings" is a real subset of "All", with both statuses.
    mine = openings.filter(designated_authority__username="manager")
    assert 0 < mine.count() < openings.count()
    assert set(mine.values_list("status", flat=True)) == {"open", "closed"}


def test_rerunning_seed_keeps_staff_changes_to_opening_status_and_authority():
    call_command("seed")
    backend = JobOpening.objects.get(title="Backend Developer")
    backend.status = JobOpening.Status.CLOSED  # staff close an open seeded opening
    backend.designated_authority = User.objects.get(username="recruiter")
    backend.save()
    ux = JobOpening.objects.get(title="UX Researcher")
    ux.status = JobOpening.Status.OPEN  # and reopen a closed one
    ux.save()

    call_command("seed")

    assert JobOpening.objects.count() == len(SEED_OPENINGS)
    backend.refresh_from_db()
    assert backend.status == JobOpening.Status.CLOSED
    assert backend.designated_authority.username == "recruiter"
    assert JobOpening.objects.get(pk=ux.pk).status == JobOpening.Status.OPEN


def test_seed_repairs_a_seeded_openings_details():
    call_command("seed")
    JobOpening.objects.filter(title="Data Engineer").update(description="Changed", location="")

    call_command("seed")

    data = JobOpening.objects.get(title="Data Engineer")
    assert data.description == "Own the pipelines that feed our reporting warehouse."
    assert data.location == "Dallas, TX"


def test_seed_records_each_application_with_its_first_history_row():
    call_command("seed")

    applications = Application.objects.select_related("opening", "source")
    assert applications.count() == len(SEED_APPLICATIONS)
    assert all(a.opening.is_open and a.source.is_active for a in applications)
    first_rows = StageChange.objects.filter(from_stage="")
    assert first_rows.count() == len(SEED_APPLICATIONS)
    assert set(first_rows.values_list("to_stage", "changed_by__username")) == {
        (Application.Stage.APPLIED, "recruiter")
    }
    referrals = applications.exclude(referred_by="")
    assert {a.source.category for a in referrals} == {Source.Category.REFERRAL}
    # Some candidates have no applications, and Ann's latest source is the referral.
    assert Candidate.objects.filter(applications__isnull=True).exists()
    ann = Candidate.objects.get(email="ann.lee@example.com")
    assert ann.applications.count() == 2
    assert prefill_source(ann).name == "Employee referral"


def test_rerunning_seed_keeps_a_staff_correction_to_an_applications_source():
    call_command("seed")
    ben = Application.objects.get(candidate__email="ben.ortiz@example.com")
    ben.source = Source.objects.get(name="Career fair")  # staff fix the source on purpose
    ben.save()

    call_command("seed")

    assert Application.objects.count() == len(SEED_APPLICATIONS)
    ben.refresh_from_db()
    assert ben.source.name == "Career fair"


def test_seed_skips_a_missing_application_whose_opening_staff_have_closed():
    call_command("seed")
    Application.objects.filter(opening__title="Data Engineer").delete()
    JobOpening.objects.filter(title="Data Engineer").update(status=JobOpening.Status.CLOSED)

    call_command("seed")

    assert not Application.objects.filter(opening__title="Data Engineer").exists()
    assert Application.objects.count() == len(SEED_APPLICATIONS) - 1


def test_seed_moves_backend_developer_applicants_into_every_column():
    call_command("seed")

    backend = Application.objects.filter(opening__title="Backend Developer")
    assert set(backend.values_list("stage", flat=True)) == set(Stage) - {Stage.HIRED}
    hired = Application.objects.get(stage=Stage.HIRED)
    assert (hired.candidate.email, hired.opening.title) == (
        "elena.rossi@example.com",
        "Product Designer",
    )
    # Every seeded move made sense under the rules: a stage history the app could have written.
    for spec in SEED_MOVES:
        application = Application.objects.get(
            candidate__email=spec.candidate, opening__title=spec.opening
        )
        assert application.stage == spec.path[-1][0]
        moves = application.stage_changes.exclude(from_stage="")
        assert moves.count() == len(spec.path)
        for move in moves:
            assert can_move(move.from_stage, move.to_stage)
            assert move.note or not requires_note(move.from_stage, move.to_stage)
            assert move.changed_by.username == spec.by


def test_rerunning_seed_never_undoes_a_staff_move():
    call_command("seed")
    recruiter = User.objects.get(username="recruiter")
    isaac = Application.objects.get(candidate__email="isaac.brown@example.com")
    move_application(isaac, Stage.SCREENING, by=recruiter)  # seed left Isaac at Applied
    ann = Application.objects.get(
        candidate__email="ann.lee@example.com", opening__title="Backend Developer"
    )
    move_application(ann, Stage.REJECTED, by=recruiter)  # seed moved Ann; staff move her on
    before = StageChange.objects.count()

    call_command("seed")

    assert StageChange.objects.count() == before
    assert Application.objects.get(pk=isaac.pk).stage == Stage.SCREENING
    assert Application.objects.get(pk=ann.pk).stage == Stage.REJECTED


def test_seed_moves_a_path_completely_or_not_at_all():
    call_command("seed")
    # Hana's path is Interview, Final Review, Offer. Make the manager a Recruiter who is no
    # longer Backend Developer's authority: the first two steps pass, and Offer is refused.
    hana = Application.objects.get(candidate__email="hana.kim@example.com")
    hana.stage_changes.exclude(from_stage="").delete()
    Application.objects.filter(pk=hana.pk).update(stage=Stage.APPLIED)
    User.objects.get(username="manager").groups.set([Group.objects.get(name="Recruiter")])
    JobOpening.objects.filter(title="Backend Developer").update(
        designated_authority=User.objects.get(username="admin")
    )

    seed_moves(next(s for s in SEED_MOVES if s.candidate == "hana.kim@example.com"))

    assert stored_path(hana) == (Stage.APPLIED, 1)


def stored_path(application) -> tuple[str, int]:
    fresh = Application.objects.get(pk=application.pk)
    return fresh.stage, fresh.stage_changes.count()


def skill_names(opening: JobOpening) -> set[str]:
    return set(opening.skills.values_list("name", flat=True))


def test_seed_lists_skills_on_every_opening_sharing_some_and_keeping_a_retired_one():
    call_command("seed")

    assert Skill.objects.count() == len(SEED_SKILLS)
    assert list(Skill.objects.retired().values_list("name", flat=True)) == ["jQuery"]
    for title, names in SEED_OPENING_SKILLS:
        assert skill_names(JobOpening.objects.get(title=title)) == set(names)
    # The same skill is shared by several openings.
    assert Skill.objects.get(name="Python").openings.count() == 3
    # A retired skill stays on the opening that listed it.
    assert "jQuery" in skill_names(JobOpening.objects.get(title="Backend Developer"))


def test_rerunning_seed_keeps_staff_changes_to_skills():
    call_command("seed")
    backend = JobOpening.objects.get(title="Backend Developer")
    backend.skills.remove(Skill.objects.get(name="jQuery"))  # staff remove a skill
    backend.skills.add(Skill.objects.create(name="Docker"))  # and add one of their own
    Skill.objects.get(name="Figma").retire()  # a Hiring Manager retires a seeded skill
    Skill.objects.get(name="jQuery").reactivate()  # and brings back the retired one
    sql = Skill.objects.get(name="SQL")
    sql.name = "sql"  # a change of capitals is the same skill
    sql.save()

    call_command("seed")

    assert skill_names(backend) == {"Python", "Django", "sql", "Docker"}
    assert Skill.objects.get(name="Figma").is_active is False
    assert Skill.objects.get(name="jQuery").is_active is True
    assert Skill.objects.count() == len(SEED_SKILLS) + 1  # Docker, and no second SQL
