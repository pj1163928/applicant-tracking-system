"""Skills on openings, and closing openings.

``attach_skill()`` and ``detach_skill()`` are how staff change an opening's
skills. Both check ``can_manage_opening_skills`` on the server, so a hand-made
POST from someone without the right is refused even though the page hides the
controls.

``close_opening()`` and ``cancel_remaining_applications()`` are how an opening
closes and how its remaining applicants are let go. Each writes an
``OpeningEvent``, checks its own permission rule, and changes stages only
through ``applications.services.move_application()``.
"""

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from accounts.permissions import can_decide_closure, can_manage_opening_skills, can_manage_openings
from applications.models import StageChange
from applications.services import move_application
from applications.stages import ACTIVE_STAGES, Stage
from notifications.models import CandidateMessage
from notifications.services import notify_authority_of_closure, send_candidate_message
from openings.models import JobOpening, OpeningEvent, OpeningSkill, Skill

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


ALREADY_CLOSED = "already_closed"
NOT_CLOSED = "not_closed"

# The note on every application that "cancel now" moves to Rejected.
CLOSURE_NOTE = "Position closed."


def close_refusal(opening: JobOpening, by: User) -> PermissionDenied | ValidationError | None:
    """Return why ``by`` can't close ``opening`` now, or None if they can.

    Admins, Recruiters and Hiring Managers may close any open opening.
    Judges ``opening.status`` as given, so ``close_opening()`` passes the stored row.
    """
    if not can_manage_openings(by):
        return PermissionDenied("Only Admins, Recruiters and Hiring Managers can close openings.")
    if not opening.is_open:
        return ValidationError(f"{opening.title} is already closed.", code=ALREADY_CLOSED)
    return None


@transaction.atomic
def close_opening(opening: JobOpening, *, by: User, note: str = "") -> OpeningEvent:
    """Close ``opening``: it stops taking new applications, and a "closed" event is written.

    Applications already in progress keep moving, including into Offer and
    Hired. If any are at an active stage, the designated authority is emailed
    (once the transaction commits) and the opening waits in their Needs
    attention panel until someone decides what happens to those applicants.

    Locks and re-reads the stored opening. Raises ``PermissionDenied`` unless
    ``by`` may manage openings, and ``ValidationError`` if it is already
    closed. Nothing is written when it refuses. Returns the new event.
    """
    stored = (
        JobOpening.objects.select_for_update()
        .select_related("designated_authority")
        .get(pk=opening.pk)
    )
    refusal = close_refusal(stored, by)
    if refusal is not None:
        raise refusal
    note = note.strip()
    stored.status = JobOpening.Status.CLOSED
    stored.save(update_fields=["status", "updated_at"])
    event = OpeningEvent.objects.create(
        opening=stored, kind=OpeningEvent.Kind.CLOSED, by=by, note=note
    )
    active_count = stored.applications.filter(stage__in=ACTIVE_STAGES).count()
    if active_count:
        notify_authority_of_closure(stored, active_count=active_count, by=by, note=note)
    opening.status, opening.updated_at = stored.status, stored.updated_at
    return event


def cancel_refusal(opening: JobOpening, by: User) -> PermissionDenied | ValidationError | None:
    """Return why ``by`` can't cancel ``opening``'s remaining applications, or None if they can.

    Only someone allowed by ``can_decide_closure`` may, and only once the
    opening is closed. Having nothing left to cancel is not a refusal: running
    it again does nothing.
    """
    if not can_decide_closure(by, opening):
        authority = opening.designated_authority
        return PermissionDenied(
            f"Only Admins, Hiring Managers or {authority.get_full_name() or authority.username}, "
            "this opening's designated authority, can decide what happens to its applicants."
        )
    if opening.is_open:
        return ValidationError(
            f"{opening.title} is open. Close it before cancelling its applications.",
            code=NOT_CLOSED,
        )
    return None


def latest_closure(opening: JobOpening) -> OpeningEvent | None:
    """Return ``opening``'s most recent "closed" event, or None if its closure wasn't recorded."""
    return opening.events.filter(kind=OpeningEvent.Kind.CLOSED).first()


@transaction.atomic
def cancel_remaining_applications(opening: JobOpening, *, by: User) -> list[StageChange]:
    """Cancel now: move every active application of closed ``opening`` to Rejected.

    Each move goes through ``move_application()`` with cause closure and the
    note "Position closed.", and each candidate is sent one cancellation email
    through ``send_candidate_message()``, keyed on this closure so it is never
    sent twice. Hired, Rejected and Withdrawn applications are left alone.
    The first cancel of each closure writes one "Remaining applications
    cancelled" event. Returns the new history rows.

    Safe to repeat: once nothing is active it changes nothing and returns an
    empty list, and a closure never gets a second cancel event. Everything
    happens in one transaction, so if any write fails none is kept.

    Locks and re-reads the stored opening, then checks ``cancel_refusal()``
    before any application changes: raises ``PermissionDenied`` unless ``by``
    may decide this opening's closure, and ``ValidationError`` if it is open.
    """
    stored = (
        JobOpening.objects.select_for_update()
        .select_related("designated_authority")
        .get(pk=opening.pk)
    )
    refusal = cancel_refusal(stored, by)
    if refusal is not None:
        raise refusal
    closure = latest_closure(stored)
    occasion = f"closure-{closure.pk}" if closure is not None else "closure-unrecorded"
    active = stored.applications.filter(stage__in=ACTIVE_STAGES).select_related("candidate")
    rows = []
    for application in active.order_by("pk"):
        rows.append(
            move_application(
                application,
                Stage.REJECTED,
                by=by,
                note=CLOSURE_NOTE,
                cause=StageChange.Cause.CLOSURE,
                expected_stage=application.stage,
            )
        )
        send_candidate_message(application, CandidateMessage.Kind.CANCELLED, occasion=occasion)
    cancelled_since = stored.events.filter(kind=OpeningEvent.Kind.APPLICATIONS_CANCELLED)
    if closure is not None:
        cancelled_since = cancelled_since.filter(pk__gt=closure.pk)
    if rows and not cancelled_since.exists():
        OpeningEvent.objects.create(
            opening=stored, kind=OpeningEvent.Kind.APPLICATIONS_CANCELLED, by=by
        )
    return rows
