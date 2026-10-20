"""Create demo data for development. Safe to run any number of times.

Later phases add their own sample data here. Every step must look records up
by a natural key and only create or update what differs, so a second run
changes nothing.
"""

from dataclasses import dataclass

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.roles import HIRING_MANAGER, INTERVIEWER, RECRUITER
from candidates.models import Candidate, Source

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


# Phase 2. Some have no phone or notes; none has applied yet (applications arrive in Phase 5).
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


class Command(BaseCommand):
    help = "Create one demo user per role, plus sample candidates and sources."

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
