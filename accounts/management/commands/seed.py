"""Create demo data for development. Safe to run any number of times.

Later phases add their own sample data here. Every step must look records up
by a natural key and only create or update what differs, so a second run
changes nothing.
"""

from dataclasses import dataclass

from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.roles import HIRING_MANAGER, INTERVIEWER, RECRUITER
from applications.models import Application
from applications.services import move_application, record_application
from applications.stages import Stage
from candidates.models import Candidate, Source
from candidates.services import archive_candidate
from openings.models import JobOpening, OpeningSkill, Skill
from openings.services import (
    cancel_remaining_applications,
    close_opening,
    find_or_create_skill,
    set_grace_period,
)

# Development-only password shared by every seeded account.
SEED_PASSWORD = "demo-pass-123"


@dataclass(frozen=True)
class SeedUser:
    username: str
    first_name: str
    last_name: str
    role: str | None  # a role group name, or None for the Admin (superuser)


SEED_USERS: tuple[SeedUser, ...] = (
    SeedUser("admin", "Avery", "Stone", None),
    SeedUser("recruiter", "Riley", "Chen", RECRUITER),
    SeedUser("manager", "Morgan", "Patel", HIRING_MANAGER),
    SeedUser("interviewer", "Jordan", "Lee", INTERVIEWER),
    # Phase 14: a second Recruiter, the authority of two openings, to demo a staff departure.
    SeedUser("taylor", "Taylor", "Brooks", RECRUITER),
)


@dataclass(frozen=True)
class SeedCandidate:
    first_name: str
    last_name: str
    email: str  # the natural key; lowercase, as the model stores it
    phone: str = ""
    notes: str = ""


# Phase 2. Some have no phone or notes. Phase 5 gives some of them applications.
SEED_CANDIDATES: tuple[SeedCandidate, ...] = (
    SeedCandidate("Ann", "Lee", "ann.lee@example.com", "555-0101", "Strong Django portfolio."),
    SeedCandidate("Ben", "Ortiz", "ben.ortiz@example.com", "555-0102"),
    SeedCandidate(
        "Chloe", "Nguyen", "chloe.nguyen@example.com", "", "Met at the spring career fair."
    ),
    SeedCandidate("Dev", "Sharma", "dev.sharma@example.com", "555-0104"),
    SeedCandidate(
        "Elena", "Rossi", "elena.rossi@example.com", "555-0105", "Prefers email contact."
    ),
    SeedCandidate("Farah", "Haddad", "farah.haddad@example.com"),
    SeedCandidate("Gus", "Lee", "gus.lee@example.com", "555-0107"),
    SeedCandidate(
        "Hana", "Kim", "hana.kim@example.com", "555-0108", "Referred by a current engineer."
    ),
    SeedCandidate("Isaac", "Brown", "isaac.brown@example.com"),
    SeedCandidate("Jade", "Okafor", "jade.okafor@example.com", "555-0110"),
    # Phase 9: withdraws from Backend Developer, then is archived (SEED_ARCHIVED).
    SeedCandidate("Kai", "Moreno", "kai.moreno@example.com", "", "Moved abroad; not looking now."),
    # Phase 13: cancelled when UX Researcher closes, then archived, so its restore list
    # shows an archived applicant who must be unarchived first.
    SeedCandidate(
        "Lena", "Park", "lena.park@example.com", "555-0112", "Paused her job search for now."
    ),
)


@dataclass(frozen=True)
class SeedSource:
    name: str  # the natural key, matched ignoring capitals as the database does
    category: str
    is_active: bool = True  # applied only when seed creates the source


# Phase 3. Every category, plus one retired source to show the retired state.
SEED_SOURCES: tuple[SeedSource, ...] = (
    SeedSource("Company careers page", Source.Category.COMPANY_WEBSITE),
    SeedSource("LinkedIn Jobs", Source.Category.JOB_BOARD),
    SeedSource("Indeed", Source.Category.JOB_BOARD),
    SeedSource("Employee referral", Source.Category.REFERRAL),
    SeedSource("Career fair", Source.Category.OTHER),
    SeedSource("Monster", Source.Category.JOB_BOARD, is_active=False),
)


@dataclass(frozen=True)
class SeedOpening:
    title: str  # (title, department) is the natural key
    department: str
    authority: str  # a seeded username; applied only when seed creates the opening
    description: str
    location: str = ""


# Phase 4. Openings split across three designated authorities, so the manager's
# "My openings" differs from "All". One has no location. Every opening starts open;
# Phases 10 and 11 close four of them through close_opening() (SEED_CLOSURES).
SEED_OPENINGS: tuple[SeedOpening, ...] = (
    SeedOpening(
        "Backend Developer",
        "Engineering",
        "manager",
        "Build and maintain our Django services and APIs.",
        "Remote",
    ),
    SeedOpening(
        "QA Analyst",
        "Engineering",
        "manager",
        "Plan and automate testing across our web products.",
        "Amarillo, TX",
    ),
    SeedOpening(
        "UX Researcher",
        "Design",
        "manager",
        "Run interviews and usability studies with our users.",
        "Remote",
    ),
    SeedOpening(
        "Data Engineer",
        "Data",
        "recruiter",
        "Own the pipelines that feed our reporting warehouse.",
        "Dallas, TX",
    ),
    SeedOpening(
        "Support Specialist",
        "Operations",
        "recruiter",
        "Help customers by phone and email, and log what they need.",
    ),
    SeedOpening(
        "Product Designer",
        "Design",
        "admin",
        "Design clear, accessible screens from first sketch to release.",
        "Austin, TX",
    ),
    # Phase 14: Taylor's openings, handed over when an Admin deactivates Taylor.
    SeedOpening(
        "Marketing Coordinator",
        "Marketing",
        "taylor",
        "Plan campaigns and keep our job ads and social posts on schedule.",
        "Amarillo, TX",
    ),
    SeedOpening(
        "Office Manager",
        "Operations",
        "taylor",
        "Keep the office running: supplies, visitors, travel and facilities.",
    ),
)


@dataclass(frozen=True)
class SeedSkill:
    name: str  # the natural key, matched ignoring capitals as the database does
    is_active: bool = True  # applied only when seed creates the skill


# Phase 8. Python, SQL, Accessibility and User research are shared by several openings.
# jQuery is retired but stays on Backend Developer, to show a retired skill on an opening.
SEED_SKILLS: tuple[SeedSkill, ...] = (
    SeedSkill("Python"),
    SeedSkill("Django"),
    SeedSkill("SQL"),
    SeedSkill("JavaScript"),
    SeedSkill("Test automation"),
    SeedSkill("Data modeling"),
    SeedSkill("Figma"),
    SeedSkill("User research"),
    SeedSkill("Accessibility"),
    SeedSkill("Customer service"),
    SeedSkill("jQuery", is_active=False),
)

# Phase 8. Each seeded opening's title, and the seeded skills it lists.
SEED_OPENING_SKILLS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Backend Developer", ("Python", "Django", "SQL", "jQuery")),
    ("QA Analyst", ("Test automation", "Python", "JavaScript")),
    ("UX Researcher", ("User research", "Accessibility")),
    ("Data Engineer", ("Python", "SQL", "Data modeling")),
    ("Support Specialist", ("Customer service",)),
    ("Product Designer", ("Figma", "Accessibility", "User research")),
    ("Marketing Coordinator", ("Customer service",)),
    ("Office Manager", ("Customer service",)),
)


@dataclass(frozen=True)
class SeedApplication:
    candidate: str  # a seeded candidate's email; (candidate, opening) is the natural key
    opening: str  # a seeded opening's title
    source: str  # a seeded source's name
    referred_by: str = ""


# Phase 5. Recorded in this order, through record_application(), by the seeded Recruiter.
# Ann applies twice, so a third application for her pre-fills her latest source
# (the referral). Phase 6 adds four more; Gus is left with no applications at all.
SEED_APPLICATIONS: tuple[SeedApplication, ...] = (
    SeedApplication("ann.lee@example.com", "Backend Developer", "LinkedIn Jobs"),
    SeedApplication("ben.ortiz@example.com", "Backend Developer", "Indeed"),
    SeedApplication("hana.kim@example.com", "Backend Developer", "Employee referral", "Sam Ortiz"),
    SeedApplication("dev.sharma@example.com", "Data Engineer", "Company careers page"),
    SeedApplication("chloe.nguyen@example.com", "Product Designer", "Career fair"),
    SeedApplication("elena.rossi@example.com", "Product Designer", "LinkedIn Jobs"),
    SeedApplication("ann.lee@example.com", "QA Analyst", "Employee referral", "Dana Lee"),
    # Phase 6: more Backend Developer applicants, so its board has someone in every column.
    SeedApplication("farah.haddad@example.com", "Backend Developer", "Indeed"),
    SeedApplication("chloe.nguyen@example.com", "Backend Developer", "Company careers page"),
    SeedApplication("isaac.brown@example.com", "Backend Developer", "LinkedIn Jobs"),
    SeedApplication("jade.okafor@example.com", "Backend Developer", "Career fair"),
    # Phase 9: Kai's application stays on the board after Kai is archived.
    SeedApplication("kai.moreno@example.com", "Backend Developer", "Indeed"),
    # Phase 10: UX Researcher's applicants, cancelled when it closes (SEED_CLOSURES).
    SeedApplication("dev.sharma@example.com", "UX Researcher", "LinkedIn Jobs"),
    SeedApplication("jade.okafor@example.com", "UX Researcher", "Company careers page"),
    # Phase 13: a third UX Researcher applicant, archived after the closure cancels her.
    SeedApplication("lena.park@example.com", "UX Researcher", "Indeed"),
    # Phase 14: someone in progress on Taylor's opening, so its new authority has work waiting.
    SeedApplication("farah.haddad@example.com", "Marketing Coordinator", "Career fair"),
)


@dataclass(frozen=True)
class SeedMove:
    candidate: str  # a seeded application's candidate email and opening title
    opening: str
    by: str  # a seeded username, who makes every move in ``path``
    path: tuple[tuple[str, str], ...]  # (stage, note) pairs, made in order


# Phase 6. Each path goes through move_application(), so it follows the stage rules:
# skips, backward moves and reopens carry a note, and only the Hiring Manager or an
# opening's authority moves into Offer or Hired. Isaac stays at Applied.
SEED_MOVES: tuple[SeedMove, ...] = (
    SeedMove(
        "ann.lee@example.com",
        "Backend Developer",
        "recruiter",
        ((Stage.SCREENING, ""), (Stage.INTERVIEW, "")),
    ),
    SeedMove(
        "ben.ortiz@example.com",
        "Backend Developer",
        "recruiter",
        (
            (Stage.REJECTED, "Missed the screening call."),
            (Stage.SCREENING, "Rescheduled: he had a family emergency that day."),
        ),
    ),
    SeedMove(
        "jade.okafor@example.com",
        "Backend Developer",
        "recruiter",
        ((Stage.SCREENING, ""), (Stage.INTERVIEW, ""), (Stage.FINAL_REVIEW, "")),
    ),
    SeedMove(
        "hana.kim@example.com",
        "Backend Developer",
        "manager",
        (
            (Stage.INTERVIEW, "Strong referral; skipped the phone screen."),
            (Stage.FINAL_REVIEW, ""),
            (Stage.OFFER, ""),
        ),
    ),
    SeedMove(
        "farah.haddad@example.com",
        "Backend Developer",
        "recruiter",
        ((Stage.REJECTED, "Looking for a more senior role than this one."),),
    ),
    SeedMove(
        "chloe.nguyen@example.com",
        "Backend Developer",
        "recruiter",
        ((Stage.WITHDRAWN, "Accepted another offer."),),
    ),
    SeedMove(
        "kai.moreno@example.com",
        "Backend Developer",
        "recruiter",
        ((Stage.WITHDRAWN, "Moving abroad for family reasons."),),
    ),
    SeedMove(
        "jade.okafor@example.com",
        "UX Researcher",
        "recruiter",
        ((Stage.SCREENING, ""),),
    ),
    SeedMove(
        "lena.park@example.com",
        "UX Researcher",
        "recruiter",
        ((Stage.SCREENING, ""), (Stage.INTERVIEW, "")),
    ),
    SeedMove(
        "elena.rossi@example.com",
        "Product Designer",
        "admin",
        (
            (Stage.SCREENING, ""),
            (Stage.INTERVIEW, ""),
            (Stage.FINAL_REVIEW, ""),
            (Stage.OFFER, ""),
            (Stage.HIRED, ""),
        ),
    ),
)


# Phase 9. Seeded candidates archived through archive_candidate() once all their seeded
# moves are made and (Phase 13) the seeded openings are closed, so Lena's UX Researcher
# application has been cancelled first. Only a candidate seed has just created is
# archived, so a re-run never re-archives one that staff have unarchived.
SEED_ARCHIVED: tuple[str, ...] = ("kai.moreno@example.com", "lena.park@example.com")


@dataclass(frozen=True)
class SeedClosure:
    opening: str  # a seeded opening's title
    by: str  # a seeded username, who closes it
    note: str
    cancel_by: str | None = None  # a seeded username who then cancels its remaining applications
    grace_days: int | None = None  # or gives them a grace period of this many days from today,
    grace_action: str = ""  # ending in this JobOpening.GraceExpiryAction, set by ``by``


# Phase 10. Closed through close_opening() once every seeded move is made, so each gets
# its "closed" event. Only an opening seed has just created is closed, so a re-run never
# closes one again. UX Researcher's applicants are cancelled (three logged emails), so
# reopening it (Phase 13) offers Dev, Jade and the archived Lena for restoring;
# QA Analyst still has Ann at Applied, so it waits in the manager's Needs attention.
# Phase 11: the recruiter, its authority, gives Data Engineer's applicant (Dev, at Applied)
# a 4-day flag-overdue grace period from the day seed runs, so `process_grace_periods
# --today` can show the 3-day reminder (day 1), the 1-day one (day 3) and the end (day 4).
SEED_CLOSURES: tuple[SeedClosure, ...] = (
    SeedClosure(
        "UX Researcher", "manager", "Research budget moved to next year.", cancel_by="manager"
    ),
    SeedClosure("Support Specialist", "recruiter", "Filled by an internal transfer."),
    SeedClosure("QA Analyst", "recruiter", "Paused until the new test lead starts."),
    SeedClosure(
        "Data Engineer",
        "recruiter",
        "Warehouse project paused for the quarter.",
        grace_days=4,
        grace_action=JobOpening.GraceExpiryAction.FLAG_OVERDUE,
    ),
)


class Command(BaseCommand):
    help = (
        "Create one demo user per role (plus a second Recruiter), sample candidates "
        "(two archived), sources, openings with skills (four of them closed, one in a grace "
        "period), and applications, some moved along the pipeline."
    )

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        for spec in SEED_USERS:
            user, created = seed_user(spec)
            action = "Created" if created else "Checked"
            self.stdout.write(f"{action} user '{user.username}'")
        new_candidates = {spec.email for spec in SEED_CANDIDATES if seed_candidate(spec)[1]}
        created = len(new_candidates)
        self.stdout.write(
            f"Candidates: {created} created, {len(SEED_CANDIDATES) - created} checked"
        )
        created = sum(seed_source(spec)[1] for spec in SEED_SOURCES)
        self.stdout.write(f"Sources: {created} created, {len(SEED_SOURCES) - created} checked")
        new_openings = {spec.title for spec in SEED_OPENINGS if seed_opening(spec)[1]}
        created = len(new_openings)
        self.stdout.write(f"Openings: {created} created, {len(SEED_OPENINGS) - created} checked")
        created = sum(seed_skill(spec)[1] for spec in SEED_SKILLS)
        self.stdout.write(f"Skills: {created} created, {len(SEED_SKILLS) - created} checked")
        results = [seed_opening_skills(title, names) for title, names in SEED_OPENING_SKILLS]
        self.stdout.write(
            f"Opening skills: {results.count(CREATED)} openings given skills, "
            f"{results.count(CHECKED)} checked"
        )
        recruiter = User.objects.get(username="recruiter")
        results = [seed_application(spec, recruiter) for spec in SEED_APPLICATIONS]
        self.stdout.write(
            f"Applications: {results.count(CREATED)} created, {results.count(CHECKED)} checked, "
            f"{results.count(SKIPPED)} skipped"
        )
        results = [seed_moves(spec) for spec in SEED_MOVES]
        self.stdout.write(
            f"Stage moves: {results.count(CREATED)} paths made, {results.count(CHECKED)} checked, "
            f"{results.count(SKIPPED)} skipped"
        )
        results = [
            seed_closure(spec, just_created=spec.opening in new_openings) for spec in SEED_CLOSURES
        ]
        self.stdout.write(
            f"Closed openings: {results.count(CREATED)} closed, "
            f"{results.count(CHECKED)} checked, {results.count(SKIPPED)} skipped"
        )
        results = [
            seed_archived(email, recruiter, just_created=email in new_candidates)
            for email in SEED_ARCHIVED
        ]
        self.stdout.write(
            f"Archived candidates: {results.count(CREATED)} archived, "
            f"{results.count(CHECKED)} checked, {results.count(SKIPPED)} skipped"
        )
        self.stdout.write(
            self.style.SUCCESS(f"Seed complete. Password for every user: {SEED_PASSWORD}")
        )


def seed_user(spec: SeedUser) -> tuple[User, bool]:
    """Create or update one seeded user so it matches ``spec``; return (user, created).

    A new user starts active. An existing one keeps its active state, because
    an Admin may have deactivated them on purpose (``deactivate_staff()``),
    after handing their openings over.
    """
    is_admin = spec.role is None
    wanted = {
        "first_name": spec.first_name,
        "last_name": spec.last_name,
        "email": f"{spec.username}@example.com",
        "is_staff": is_admin,
        "is_superuser": is_admin,
    }
    user, created = User.objects.get_or_create(
        username=spec.username, defaults=wanted | {"is_active": True}
    )

    changed = [field for field, value in wanted.items() if getattr(user, field) != value]
    for field in changed:
        setattr(user, field, wanted[field])
    if not user.check_password(SEED_PASSWORD):
        user.set_password(SEED_PASSWORD)
        changed.append("password")
    if changed:
        user.save(update_fields=changed)

    groups = [] if is_admin else [Group.objects.get(name=spec.role)]
    user.groups.set(groups)
    return user, created


def seed_candidate(spec: SeedCandidate) -> tuple[Candidate, bool]:
    """Create or update one seeded candidate, found by email; return (candidate, created)."""
    wanted = {
        "first_name": spec.first_name,
        "last_name": spec.last_name,
        "phone": spec.phone,
        "notes": spec.notes,
    }
    candidate, created = Candidate.objects.get_or_create(email=spec.email, defaults=wanted)

    changed = [field for field, value in wanted.items() if getattr(candidate, field) != value]
    for field in changed:
        setattr(candidate, field, wanted[field])
    if changed:
        candidate.save(update_fields=[*changed, "updated_at"])
    return candidate, created


def seed_source(spec: SeedSource) -> tuple[Source, bool]:
    """Create one seeded source if no source has its name (ignoring case); return (source, created).

    An existing source keeps its name's capitals and its active or retired
    state, because staff may have renamed or retired it on purpose. Only a
    drifted category is repaired, since the app can't change categories.
    """
    source = Source.objects.filter(name__iexact=spec.name).first()
    if source is None:
        source = Source.objects.create(
            name=spec.name, category=spec.category, is_active=spec.is_active
        )
        return source, True
    if source.category != spec.category:
        source.category = spec.category
        source.save(update_fields=["category"])
    return source, False


def seed_opening(spec: SeedOpening) -> tuple[JobOpening, bool]:
    """Create or update one seeded opening, found by (title, department); return (opening, created).

    The designated authority is set only when seed creates the opening, and
    the status is never touched, because staff close openings and (later)
    reassign them on purpose. New openings start open; ``seed_closure()``
    closes the seeded closed ones. Drifted details (location, description)
    are repaired.
    """
    wanted = {"location": spec.location, "description": spec.description}
    opening, created = JobOpening.objects.get_or_create(
        title=spec.title,
        department=spec.department,
        defaults=wanted | {"designated_authority": User.objects.get(username=spec.authority)},
    )
    if created:
        return opening, True

    changed = [field for field, value in wanted.items() if getattr(opening, field) != value]
    for field in changed:
        setattr(opening, field, wanted[field])
    if changed:
        opening.save(update_fields=[*changed, "updated_at"])
    return opening, False


CREATED, CHECKED, SKIPPED = "created", "checked", "skipped"


def seed_skill(spec: SeedSkill) -> tuple[Skill, bool]:
    """Create one seeded skill if no skill has its name (ignoring case); return (skill, created).

    An existing skill keeps its name's capitals and its active or retired
    state, because staff may have retired or reactivated it on purpose.
    """
    skill, created = find_or_create_skill(spec.name)
    if created and not spec.is_active:
        skill.retire()
    return skill, created


def seed_opening_skills(title: str, names: tuple[str, ...]) -> str:
    """Give one seeded opening its seeded skills if it lists none yet; return CREATED or CHECKED.

    An opening that already lists any skill is left as it is, since staff may
    have added or removed skills on purpose. The skills are linked directly,
    not through ``attach_skill()``: seed recreates a history in which jQuery
    was listed before it was retired, which staff could no longer do today.
    """
    department = next(o.department for o in SEED_OPENINGS if o.title == title)
    opening = JobOpening.objects.get(title=title, department=department)
    if opening.skills.exists():
        return CHECKED
    OpeningSkill.objects.bulk_create(
        OpeningSkill(opening=opening, skill=Skill.objects.named(name).get()) for name in names
    )
    return CREATED


def seed_application(spec: SeedApplication, by: User) -> str:
    """Record one seeded application unless it exists; return CREATED, CHECKED or SKIPPED.

    An existing application is left exactly as it is, since staff may have
    corrected its source on purpose. A missing one goes through
    ``record_application()``, so it gets its first history row; if staff have
    since closed the opening or retired the source, it is skipped.
    """
    candidate = Candidate.objects.get(email=spec.candidate)
    department = next(o.department for o in SEED_OPENINGS if o.title == spec.opening)
    opening = JobOpening.objects.get(title=spec.opening, department=department)
    if Application.objects.filter(candidate=candidate, opening=opening).exists():
        return CHECKED
    source = Source.objects.get(name__iexact=spec.source)
    try:
        record_application(
            candidate=candidate,
            opening=opening,
            source=source,
            by=by,
            referred_by=spec.referred_by,
        )
    except ValidationError:
        return SKIPPED
    return CREATED


def seed_moves(spec: SeedMove) -> str:
    """Make one seeded application's moves unless it has moved before; return the outcome.

    Returns CREATED when the whole path is made, CHECKED when the application
    has already moved (by an earlier seed or by staff, whose moves are never
    undone) or doesn't exist, and SKIPPED when the stage rules refuse a step,
    in which case none of the path is kept. Every step goes through
    ``move_application()``, so it gets its history row.
    """
    application = Application.objects.filter(
        candidate__email=spec.candidate, opening__title=spec.opening
    ).first()
    if application is None or application.stage_changes.count() > 1:
        return CHECKED
    by = User.objects.get(username=spec.by)
    try:
        with transaction.atomic():
            for stage, note in spec.path:
                move_application(application, stage, by=by, note=note)
    except (ValidationError, PermissionDenied):
        return SKIPPED
    return CREATED


def seed_archived(email: str, by: User, *, just_created: bool) -> str:
    """Archive one seeded candidate that this run created; return CREATED, CHECKED or SKIPPED.

    A candidate from an earlier run is left as it is (CHECKED), archived or
    not, because staff may have unarchived them on purpose. The archive goes
    through ``archive_candidate()``, so it is SKIPPED if one of their
    applications is still active.
    """
    if not just_created:
        return CHECKED
    try:
        archive_candidate(Candidate.objects.get(email=email), by=by)
    except ValidationError:
        return SKIPPED
    return CREATED


def seed_closure(spec: SeedClosure, *, just_created: bool) -> str:
    """Close one seeded opening that this run created; return CREATED, CHECKED or SKIPPED.

    An opening from an earlier run is left as it is (CHECKED), open or closed,
    because staff may have closed it, or (later) reopened it, on purpose. The
    close goes through ``close_opening()``, any cancel through
    ``cancel_remaining_applications()`` and any grace period through
    ``set_grace_period()``, so each writes its events and emails each candidate
    once. The grace period is set only in this run, so a re-run never sets or
    resets one that staff have since extended.
    """
    if not just_created:
        return CHECKED
    department = next(o.department for o in SEED_OPENINGS if o.title == spec.opening)
    opening = JobOpening.objects.get(title=spec.opening, department=department)
    try:
        with transaction.atomic():  # the close and its cancel happen together, or neither does
            close_opening(opening, by=User.objects.get(username=spec.by), note=spec.note)
            if spec.cancel_by:
                cancel_by = User.objects.get(username=spec.cancel_by)
                cancel_remaining_applications(opening, by=cancel_by)
            if spec.grace_days:
                set_grace_period(
                    opening,
                    days=spec.grace_days,
                    action=spec.grace_action,
                    by=User.objects.get(username=spec.by),
                )
    except (ValidationError, PermissionDenied):
        return SKIPPED
    return CREATED
