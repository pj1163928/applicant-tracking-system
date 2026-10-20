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


class Command(BaseCommand):
    help = "Create one demo user per role (and, in later phases, sample data)."

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        for spec in SEED_USERS:
            user, created = seed_user(spec)
            action = "Created" if created else "Checked"
            self.stdout.write(f"{action} user '{user.username}'")
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
