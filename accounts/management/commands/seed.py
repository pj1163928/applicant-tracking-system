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
from openings.models import JobOpening

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
    status: str = JobOpening.Status.OPEN  # applied only when seed creates the opening


# Phase 4. Open and closed openings, split across three designated authorities, so
# the manager's "My openings" differs from "All". One has no location.
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
        JobOpening.Status.CLOSED,
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
        status=JobOpening.Status.CLOSED,
    ),
    SeedOpening(
        "Product Designer",
        "Design",
        "admin",
        "Design clear, accessible screens from first sketch to release.",
        "Austin, TX",
    ),
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


class Command(BaseCommand):
    help = (
        "Create one demo user per role, plus sample candidates, sources, openings and "
        "applications, some moved along the pipeline."
    )

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        for spec in SEED_USERS:
            user, created = seed_user(spec)
            action = "Created" if created else "Checked"
            self.stdout.write(f"{action} user '{user.username}'")
        created = sum(seed_candidate(spec)[1] for spec in SEED_CANDIDATES)
        self.stdout.write(
            f"Candidates: {created} created, {len(SEED_CANDIDATES) - created} checked"
        )
        created = sum(seed_source(spec)[1] for spec in SEED_SOURCES)
        self.stdout.write(f"Sources: {created} created, {len(SEED_SOURCES) - created} checked")
        created = sum(seed_opening(spec)[1] for spec in SEED_OPENINGS)
        self.stdout.write(f"Openings: {created} created, {len(SEED_OPENINGS) - created} checked")
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
        self.stdout.write(
            self.style.SUCCESS(f"Seed complete. Password for every user: {SEED_PASSWORD}")
        )


def seed_user(spec: SeedUser) -> tuple[User, bool]:
    """Create or update one seeded user so it matches ``spec``; return (user, created)."""
    is_admin = spec.role is None
    wanted = {
        "first_name": spec.first_name,
        "last_name": spec.last_name,
        "email": f"{spec.username}@example.com",
        "is_active": True,
        "is_staff": is_admin,
        "is_superuser": is_admin,
    }
    user, created = User.objects.get_or_create(username=spec.username, defaults=wanted)

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

    Status and designated authority are set only when seed creates the
    opening, because staff close openings and (later) reassign them on
    purpose. Drifted details (location, description) are repaired.
    """
    wanted = {"location": spec.location, "description": spec.description}
    opening, created = JobOpening.objects.get_or_create(
        title=spec.title,
        department=spec.department,
        defaults=wanted
        | {
            "status": spec.status,
            "designated_authority": User.objects.get(username=spec.authority),
        },
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
