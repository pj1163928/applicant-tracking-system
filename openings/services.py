"""Skills on openings: attaching and detaching them, and creating new ones inline.

``attach_skill()`` and ``detach_skill()`` are how staff change an opening's
skills. Both check ``can_manage_opening_skills`` on the server, so a hand-made
POST from someone without the right is refused even though the page hides the
controls.
"""

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from accounts.permissions import can_manage_opening_skills
from openings.models import JobOpening, OpeningSkill, Skill

ALREADY_LISTED = "already_listed"
BLANK_SKILL = "blank_skill"
RETIRED_SKILL = "retired_skill"
SKILL_TOO_LONG = "skill_too_long"

SKILL_NAME_MAX_LENGTH = Skill._meta.get_field("name").max_length


def clean_skill_name(name: str) -> str:
    """Return ``name`` as a skill is stored: no spaces around it, and single spaces inside.

    Capitals are kept as typed; only uniqueness ignores them.
    """
    return " ".join(name.split())


def find_or_create_skill(name: str) -> tuple[Skill, bool]:
    """Return the skill called ``name`` (ignoring capitals and extra spaces), creating it if none.

    Returns (skill, created). An existing skill keeps its own capitals, so
    "python" finds "Python" and never adds a near-duplicate. A retired skill is
    returned as it is; callers decide whether it may be used. Doesn't check
    permissions: ``attach_skill()`` does.
    """
    name = clean_skill_name(name)
    skill = Skill.objects.named(name).first()
    if skill is not None:
        return skill, False
    try:
        with transaction.atomic():
            return Skill.objects.create(name=name), True
    except IntegrityError:
        # Another request created the same name first; anything else is a real error.
        skill = Skill.objects.named(name).first()
        if skill is None:
            raise
        return skill, False


def manage_refusal(opening: JobOpening, by: User) -> PermissionDenied | None:
    """Return why ``by`` can't change ``opening``'s skills, or None if they can."""
    if can_manage_opening_skills(by, opening):
        return None
    authority = opening.designated_authority
    return PermissionDenied(
        f"Only Admins, Hiring Managers or {authority.get_full_name() or authority.username}, "
        "this opening's designated authority, can change its skills."
    )


@transaction.atomic
def attach_skill(opening: JobOpening, name: str, *, by: User) -> Skill:
    """Add the skill called ``name`` to ``opening``, creating the skill if it doesn't exist yet.

    The name is matched ignoring capitals and extra spaces, so typing "python"
    when "Python" exists attaches the existing skill. A new skill keeps the
    capitals it was typed with. Returns the attached skill.

    Raises ``PermissionDenied`` unless ``by`` may manage this opening's skills,
    and ``ValidationError`` if the name is blank or too long, the skill is
    retired, or the opening already lists it. Nothing is written when it refuses.
    """
    refusal = manage_refusal(opening, by)
    if refusal is not None:
        raise refusal
    name = clean_skill_name(name)
    if not name:
        raise ValidationError("Type a skill name.", code=BLANK_SKILL)
    if len(name) > SKILL_NAME_MAX_LENGTH:
        raise ValidationError(
            f"Skill names can be at most {SKILL_NAME_MAX_LENGTH} characters.", code=SKILL_TOO_LONG
        )
    existing = Skill.objects.named(name).first()
    if existing is not None and not existing.is_active:
        raise ValidationError(
            f"{existing.name} is retired, so it can't be added to openings.", code=RETIRED_SKILL
        )
    if existing is not None and opening.skills.filter(pk=existing.pk).exists():
        raise ValidationError(
            f"{opening.title} already lists {existing.name}.", code=ALREADY_LISTED
        )
    skill = existing or find_or_create_skill(name)[0]
    try:
        with transaction.atomic():
            OpeningSkill.objects.create(opening=opening, skill=skill)
    except IntegrityError:
        # Another request attached it first; anything else is a real error.
        if not opening.skills.filter(pk=skill.pk).exists():
            raise
        raise ValidationError(
            f"{opening.title} already lists {skill.name}.", code=ALREADY_LISTED
        ) from None
    return skill


def detach_skill(opening: JobOpening, skill: Skill, *, by: User) -> bool:
    """Remove ``skill`` from ``opening``; return False if the opening didn't list it.

    Retired skills can be removed too, though they then can't be added back.
    The skill itself is kept for other openings. Raises ``PermissionDenied``
    unless ``by`` may manage this opening's skills.
    """
    refusal = manage_refusal(opening, by)
    if refusal is not None:
        raise refusal
    deleted, _ = OpeningSkill.objects.filter(opening=opening, skill=skill).delete()
    return deleted > 0
