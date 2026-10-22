"""Skills on openings, and closing openings.

``attach_skill()`` and ``detach_skill()`` are how staff change an opening's
skills. Both check ``can_manage_opening_skills`` on the server, so a hand-made
POST from someone without the right is refused even though the page hides the
controls.

``close_opening()`` and ``cancel_remaining_applications()`` are how an opening
closes and how its remaining applicants are let go. ``set_grace_period()`` and
``extend_grace_period()`` give them time instead, and ``process_grace_periods()``
(run daily by the ``process_grace_periods`` command) sends the reminders and
handles each grace period's end. ``reopen_opening()`` opens it again, and
``restore_applications()`` puts applicants cancelled at its latest closure back
where they were. Each writes an ``OpeningEvent``, checks its own permission
rule, and changes stages only through ``applications.services.move_application()``.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateformat import format as format_date

from accounts.permissions import can_decide_closure, can_manage_opening_skills, can_manage_openings
from applications.models import Application, StageChange
from applications.services import ARCHIVED_CANDIDATE, move_application, move_refusal
from applications.stages import ACTIVE_STAGES, Stage
from notifications.models import CandidateMessage
from notifications.services import (
    notify_authority_of_closure,
    notify_authority_of_overdue,
    send_candidate_message,
)
from openings.grace import due_reminder, grace_period_has_ended
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


def decide_refusal(opening: JobOpening, by: User) -> PermissionDenied | None:
    """Return why ``by`` can't decide what happens to ``opening``'s applicants, or None."""
    if can_decide_closure(by, opening):
        return None
    authority = opening.designated_authority
    return PermissionDenied(
        f"Only Admins, Hiring Managers or {authority.get_full_name() or authority.username}, "
        "this opening's designated authority, can decide what happens to its applicants."
    )


def cancel_refusal(opening: JobOpening, by: User) -> PermissionDenied | ValidationError | None:
    """Return why ``by`` can't cancel ``opening``'s remaining applications, or None if they can.

    Only someone allowed by ``can_decide_closure`` may, and only once the
    opening is closed. Having nothing left to cancel is not a refusal: running
    it again does nothing.
    """
    refusal = decide_refusal(opening, by)
    if refusal is not None:
        return refusal
    if opening.is_open:
        return ValidationError(
            f"{opening.title} is open. Close it before cancelling its applications.",
            code=NOT_CLOSED,
        )
    return None


def latest_closure(opening: JobOpening) -> OpeningEvent | None:
    """Return ``opening``'s most recent "closed" event, or None if its closure wasn't recorded."""
    return opening.events.filter(kind=OpeningEvent.Kind.CLOSED).first()


def latest_reopening(opening: JobOpening) -> OpeningEvent | None:
    """Return ``opening``'s most recent "reopened" event, or None if it was never reopened."""
    return opening.events.filter(kind=OpeningEvent.Kind.REOPENED).first()


def closure_occasion(opening: JobOpening) -> str:
    """Name ``opening``'s latest closure, for the identity of the candidate emails it causes."""
    closure = latest_closure(opening)
    return f"closure-{closure.pk}" if closure is not None else "closure-unrecorded"


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
    occasion = closure_occasion(stored)
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
                closure=closure,
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


GRACE_PERIOD_EXISTS = "grace_period_exists"
NO_GRACE_PERIOD = "no_grace_period"
NOTHING_IN_PROGRESS = "nothing_in_progress"
INVALID_GRACE_DAYS = "invalid_grace_days"
INVALID_EXPIRY_ACTION = "invalid_expiry_action"
INVALID_GRACE_END = "invalid_grace_end"
GRACE_ALREADY_CANCELLED = "grace_already_cancelled"
NOTE_REQUIRED = "note_required"

# How long a grace period may be, in days, when set and (from today) when extended.
GRACE_DAYS_MIN = 1
GRACE_DAYS_MAX = 90

GRACE_FIELDS = (
    "grace_period_ends",
    "grace_expiry_action",
    "grace_period_set_on",
    "grace_expired_on",
)


def display_date(day: date) -> str:
    """``day`` as event notes show it, such as "Nov 3, 2026"."""
    return format_date(day, "M j, Y")


def plural_days(count: int) -> str:
    """``count`` days, such as "1 day" or "7 days"."""
    return f"{count} day{'' if count == 1 else 's'}"


def grace_details(opening: JobOpening) -> dict:
    """What a candidate's grace-period emails say about ``opening``'s grace period."""
    return {
        "ends": opening.grace_period_ends,
        "auto_cancel": opening.grace_expiry_action == JobOpening.GraceExpiryAction.AUTO_CANCEL,
    }


def copy_grace_fields(source: JobOpening, target: JobOpening) -> None:
    """Copy the stored grace period onto the caller's copy of the opening."""
    for name in (*GRACE_FIELDS, "updated_at"):
        setattr(target, name, getattr(source, name))


def set_grace_refusal(
    opening: JobOpening, by: User, *, days: int, action: str
) -> PermissionDenied | ValidationError | None:
    """Return why ``by`` can't give ``opening`` a grace period of ``days`` now, or None.

    Only someone allowed by ``can_decide_closure`` may, only on a closed
    opening with applicants still in progress, and only once per closure: an
    existing grace period is extended instead. ``days`` is 1–90, and ``action``
    one of ``JobOpening.GraceExpiryAction``.
    """
    refusal = decide_refusal(opening, by)
    if refusal is not None:
        return refusal
    if opening.is_open:
        return ValidationError(
            f"{opening.title} is open. Close it before giving its applicants a grace period.",
            code=NOT_CLOSED,
        )
    if opening.has_grace_period:
        return ValidationError(
            f"{opening.title} already has a grace period. Extend it instead.",
            code=GRACE_PERIOD_EXISTS,
        )
    if not opening.applications.filter(stage__in=ACTIVE_STAGES).exists():
        return ValidationError(
            f"No applicants for {opening.title} are still in progress.", code=NOTHING_IN_PROGRESS
        )
    if not GRACE_DAYS_MIN <= days <= GRACE_DAYS_MAX:
        return ValidationError(
            f"A grace period is {GRACE_DAYS_MIN} to {GRACE_DAYS_MAX} days.",
            code=INVALID_GRACE_DAYS,
        )
    if action not in JobOpening.GraceExpiryAction.values:
        return ValidationError(
            "Choose what happens when the grace period ends.", code=INVALID_EXPIRY_ACTION
        )
    return None


@transaction.atomic
def set_grace_period(
    opening: JobOpening, *, days: int, action: str, by: User, today: date | None = None
) -> OpeningEvent:
    """Give closed ``opening``'s remaining applicants ``days`` more days, then apply ``action``.

    The grace period ends on ``today`` + ``days`` (calendar days in the project
    time zone; ``today`` defaults to ``timezone.localdate()``), when
    ``process_grace_periods()`` either cancels the remaining applications or
    flags the opening as overdue. Writes a "grace period set" event and emails
    every candidate still in progress once, keyed on this closure.

    Locks and re-reads the stored opening, then checks ``set_grace_refusal()``:
    raises ``PermissionDenied`` unless ``by`` may decide this opening's
    closure, and ``ValidationError`` for anything else it refuses. Nothing is
    written when it refuses. Returns the new event.
    """
    today = today or timezone.localdate()
    stored = (
        JobOpening.objects.select_for_update()
        .select_related("designated_authority")
        .get(pk=opening.pk)
    )
    refusal = set_grace_refusal(stored, by, days=days, action=action)
    if refusal is not None:
        raise refusal
    stored.grace_period_ends = today + timedelta(days=days)
    stored.grace_expiry_action = action
    stored.grace_period_set_on = today
    stored.grace_expired_on = None
    stored.save(update_fields=[*GRACE_FIELDS, "updated_at"])
    then = JobOpening.GraceExpiryAction(action).label
    event = OpeningEvent.objects.create(
        opening=stored,
        kind=OpeningEvent.Kind.GRACE_PERIOD_SET,
        by=by,
        note=(
            f"{plural_days(days)}, ending {display_date(stored.grace_period_ends)}. "
            f"When it ends: {then[0].lower()}{then[1:]}."
        ),
    )
    occasion = closure_occasion(stored)
    active = stored.applications.filter(stage__in=ACTIVE_STAGES).select_related("candidate")
    for application in active.order_by("pk"):
        send_candidate_message(
            application,
            CandidateMessage.Kind.GRACE_PERIOD_SET,
            occasion=occasion,
            context=grace_details(stored),
        )
    copy_grace_fields(stored, opening)
    return event


def extend_refusal(
    opening: JobOpening, by: User, *, ends: date, note: str, today: date
) -> PermissionDenied | ValidationError | None:
    """Return why ``by`` can't move ``opening``'s grace period to end on ``ends``, or None.

    Only someone allowed by ``can_decide_closure`` may, while the grace period
    is running or overdue; once an auto-cancel grace period has ended there is
    nothing left to extend. ``ends`` must be after both the current end and
    ``today``, at most 90 days from ``today``, and ``note`` must say why.
    """
    refusal = decide_refusal(opening, by)
    if refusal is not None:
        return refusal
    if opening.is_open:
        return ValidationError(
            f"{opening.title} is open, so it has no grace period.", code=NOT_CLOSED
        )
    if not opening.has_grace_period:
        return ValidationError(
            f"{opening.title} has no grace period to extend.", code=NO_GRACE_PERIOD
        )
    if opening.auto_cancelled:
        return ValidationError(
            f"The grace period for {opening.title} has ended and its applications were "
            "cancelled, so it can't be extended.",
            code=GRACE_ALREADY_CANCELLED,
        )
    if not note.strip():
        return ValidationError("Say why the grace period is being extended.", code=NOTE_REQUIRED)
    earliest, latest = extend_bounds(opening, today=today)
    if not earliest <= ends <= latest:
        return ValidationError(
            f"Pick an end date from {display_date(earliest)} to {display_date(latest)}.",
            code=INVALID_GRACE_END,
        )
    return None


def extend_bounds(opening: JobOpening, *, today: date) -> tuple[date, date]:
    """Return the first and last end dates ``opening``'s grace period may be extended to.

    The new end is after both the current end and ``today``, and at most 90
    days from ``today``.
    """
    earliest = max(opening.grace_period_ends, today) + timedelta(days=1)
    return earliest, today + timedelta(days=GRACE_DAYS_MAX)


@transaction.atomic
def extend_grace_period(
    opening: JobOpening, *, ends: date, note: str, by: User, today: date | None = None
) -> OpeningEvent:
    """Move ``opening``'s grace period to end on ``ends``, with a note saying why.

    Works while the grace period is running and once a flag-overdue one has
    ended (the opening then stops being overdue). Candidates get no email now,
    but their reminders follow the new end date. Writes a "grace period
    extended" event whose note gives both dates and the reason.

    Locks and re-reads the stored opening, then checks ``extend_refusal()``:
    raises ``PermissionDenied`` unless ``by`` may decide this opening's
    closure, and ``ValidationError`` for anything else it refuses. Nothing is
    written when it refuses. Returns the new event.
    """
    today = today or timezone.localdate()
    stored = (
        JobOpening.objects.select_for_update()
        .select_related("designated_authority")
        .get(pk=opening.pk)
    )
    refusal = extend_refusal(stored, by, ends=ends, note=note, today=today)
    if refusal is not None:
        raise refusal
    previous = stored.grace_period_ends
    stored.grace_period_ends = ends
    stored.grace_period_set_on = today
    stored.grace_expired_on = None
    stored.save(update_fields=[*GRACE_FIELDS, "updated_at"])
    event = OpeningEvent.objects.create(
        opening=stored,
        kind=OpeningEvent.Kind.GRACE_PERIOD_EXTENDED,
        by=by,
        note=(
            f"Extended from {display_date(previous)} to {display_date(ends)}. "
            f"Reason: {note.strip()}"
        ),
    )
    copy_grace_fields(stored, opening)
    return event


@dataclass
class GraceRun:
    """What one ``process_grace_periods()`` run did, for the command to report."""

    reminders_sent: int = 0
    expired: list[str] = field(default_factory=list)  # titles of openings whose grace period ended
    warnings: list[str] = field(default_factory=list)  # openings skipped, and why


def process_grace_periods(*, today: date | None = None) -> GraceRun:
    """Send the grace-period reminders due on ``today`` and handle each grace period that ends.

    ``today`` defaults to ``timezone.localdate()``. Each running grace period
    is handled in its own transaction, with the opening locked and re-read
    first. A reminder (3 or 1 days left, by ``openings.grace.due_reminder``)
    goes to every application still active at that moment, keyed on the
    closure, the end date and the days left, so it is never sent twice and an
    extension leads to fresh reminders.

    From the end date on (``today >= grace_period_ends``) the grace period
    ends instead, through ``expire_grace_period()``. That sets
    ``grace_expired_on``, so the end-of-period action happens only once.

    Safe to run any number of times: a second run on the same day sends and
    writes nothing.
    """
    today = today or timezone.localdate()
    run = GraceRun()
    pks = JobOpening.objects.with_grace_period_running().order_by("pk").values_list("pk", flat=True)
    for pk in pks:
        with transaction.atomic():
            stored = (
                JobOpening.objects.with_grace_period_running()
                .select_for_update()
                .select_related("designated_authority")
                .filter(pk=pk)
                .first()
            )
            if stored is None:  # changed since the list was read
                continue
            if not grace_period_has_ended(ends=stored.grace_period_ends, today=today):
                run.reminders_sent += send_due_reminders(stored, today=today)
            elif expire_grace_period(stored, today=today):
                run.expired.append(stored.title)
            else:
                run.warnings.append(
                    f"Skipped {stored.title}: neither the person who set its grace period nor "
                    "its designated authority can decide its closure any more."
                )
    return run


def grace_decider(opening: JobOpening) -> User | None:
    """Return who the end of ``opening``'s grace period is recorded as done by, or None.

    That is the person who set it, while ``can_decide_closure`` still allows
    them; otherwise the designated authority, if it allows them; otherwise
    nobody, and the end waits for a later run.
    """
    set_events = opening.events.filter(kind=OpeningEvent.Kind.GRACE_PERIOD_SET)
    closure = latest_closure(opening)
    if closure is not None:
        set_events = set_events.filter(pk__gt=closure.pk)
    set_event = set_events.select_related("by").first()
    setter = set_event.by if set_event is not None else None
    for person in (setter, opening.designated_authority):
        if person is not None and can_decide_closure(person, opening):
            return person
    return None


def expire_grace_period(opening: JobOpening, *, today: date) -> bool:
    """End ``opening``'s grace period on ``today`` and apply its expiry action, once.

    Auto-cancel goes through ``cancel_remaining_applications()``, which
    rejects the active applications and emails each candidate. Flag overdue
    leaves them as they are and emails the designated authority, if anyone is
    still in progress. Either way a "grace period ended" event is written and
    ``grace_expired_on`` set, so this never happens twice for the same end
    date. Expects ``opening`` locked and re-read inside the caller's
    transaction. Returns False, and changes nothing, if ``grace_decider()``
    finds nobody to record it as done by.
    """
    by = grace_decider(opening)
    if by is None:
        return False
    active_count = opening.applications.filter(stage__in=ACTIVE_STAGES).count()
    in_progress = (
        f"{active_count} applicant{'' if active_count == 1 else 's'} still in progress"
        if active_count
        else "nobody still in progress"
    )
    auto_cancel = opening.grace_expiry_action == JobOpening.GraceExpiryAction.AUTO_CANCEL
    opening.grace_expired_on = today
    opening.save(update_fields=["grace_expired_on", "updated_at"])
    then = "The remaining applications were cancelled." if auto_cancel else "Flagged as overdue."
    OpeningEvent.objects.create(
        opening=opening,
        kind=OpeningEvent.Kind.GRACE_PERIOD_EXPIRED,
        by=by,
        note=f"Ended {display_date(opening.grace_period_ends)} with {in_progress}. {then}",
    )
    if auto_cancel:
        cancel_remaining_applications(opening, by=by)
    else:
        notify_authority_of_overdue(opening, active_count=active_count)
    return True


def send_due_reminders(opening: JobOpening, *, today: date) -> int:
    """Send ``opening``'s reminder due on ``today`` to each active candidate; return how many."""
    days_left = due_reminder(
        ends=opening.grace_period_ends, set_on=opening.grace_period_set_on, today=today
    )
    if days_left is None:
        return 0
    occasion = (
        f"{closure_occasion(opening)}-ends-{opening.grace_period_ends.isoformat()}-{days_left}d"
    )
    active = opening.applications.filter(stage__in=ACTIVE_STAGES).select_related("candidate")
    sent = 0
    for application in active.order_by("pk"):
        message = send_candidate_message(
            application,
            CandidateMessage.Kind.GRACE_REMINDER,
            occasion=occasion,
            context=grace_details(opening) | {"days_left": days_left},
        )
        sent += message is not None
    return sent


ALREADY_OPEN = "already_open"
NOT_OPEN = "not_open"
NOT_RESTORABLE = "not_restorable"

# The note on every application a restore puts back after a reopening.
REOPEN_NOTE = "Position reopened."


def reopen_refusal(opening: JobOpening, by: User) -> PermissionDenied | ValidationError | None:
    """Return why ``by`` can't reopen ``opening`` now, or None if they can.

    Anyone who may close an opening may reopen it: Admins, Recruiters and
    Hiring Managers. Judges ``opening.status`` as given, so ``reopen_opening()``
    passes the stored row.
    """
    if not can_manage_openings(by):
        return PermissionDenied("Only Admins, Recruiters and Hiring Managers can reopen openings.")
    if opening.is_open:
        return ValidationError(f"{opening.title} is already open.", code=ALREADY_OPEN)
    return None


@transaction.atomic
def reopen_opening(opening: JobOpening, *, by: User, note: str = "") -> OpeningEvent:
    """Reopen closed ``opening``: it takes new applications again, with a "reopened" event.

    Any grace period is cleared, so no more reminders go out and its end never
    runs. Applications still in progress carry on as they are. Applicants
    cancelled at the latest closure stay Rejected until someone allowed by
    ``can_decide_closure`` restores them (``restore_applications()``); until
    that choice is made the opening waits in its authority's Needs attention.

    Locks and re-reads the stored opening. Raises ``PermissionDenied`` unless
    ``by`` may manage openings, and ``ValidationError`` if it is already open.
    Nothing is written when it refuses. Returns the new event.
    """
    stored = (
        JobOpening.objects.select_for_update()
        .select_related("designated_authority")
        .get(pk=opening.pk)
    )
    refusal = reopen_refusal(stored, by)
    if refusal is not None:
        raise refusal
    lines = [note.strip()] if note.strip() else []
    if stored.grace_period_running:
        lines.append(f"Cleared the grace period ending {display_date(stored.grace_period_ends)}.")
    stored.status = JobOpening.Status.OPEN
    stored.grace_period_ends = None
    stored.grace_expiry_action = ""
    stored.grace_period_set_on = None
    stored.grace_expired_on = None
    stored.save(update_fields=["status", *GRACE_FIELDS, "updated_at"])
    event = OpeningEvent.objects.create(
        opening=stored, kind=OpeningEvent.Kind.REOPENED, by=by, note="\n".join(lines)
    )
    copy_grace_fields(stored, opening)
    opening.status = stored.status
    return event


def restorable_cancellations(opening: JobOpening):
    """Return the cancellations from ``opening``'s latest closure that a restore may undo.

    One ``StageChange`` row per application: its cancellation (cause closure)
    at the latest closure, while the application is still at Rejected because
    of it. The row's ``from_stage`` is the stage a restore puts it back to.
    Applications cancelled at an earlier closure, or moved since, are left out.
    """
    closure = latest_closure(opening)
    if closure is None:
        return StageChange.objects.none()
    return StageChange.objects.cancellations_to_restore().filter(
        closure=closure, application__opening=opening
    )


def restore_refusal(opening: JobOpening, by: User) -> PermissionDenied | ValidationError | None:
    """Return why ``by`` can't restore any of ``opening``'s applicants now, or None.

    Only someone allowed by ``can_decide_closure`` may, and only once the
    opening has been reopened.
    """
    refusal = decide_refusal(opening, by)
    if refusal is not None:
        return refusal
    if not opening.is_open:
        return ValidationError(
            f"{opening.title} is closed. Reopen it before restoring its applicants.",
            code=NOT_OPEN,
        )
    return None


@dataclass(frozen=True)
class RestoreChoice:
    """One applicant cancelled at an opening's latest closure, as the restore checklist shows them.

    ``stage`` is where restoring puts the application back; ``refusal`` is why
    the user can't restore it, short enough for the checklist ("" if they can).
    """

    application: Application
    stage: Stage
    refusal: str = ""

    @property
    def selectable(self) -> bool:
        return not self.refusal


def restore_choices(opening: JobOpening, by: User) -> list[RestoreChoice]:
    """Return the applicants a restore of ``opening`` may undo, by name, each checked for ``by``.

    Every application ``restorable_cancellations()`` finds is listed, including
    ones ``by`` can't restore, so the checklist can show them disabled with the reason.
    """
    rows = (
        restorable_cancellations(opening)
        .select_related("application__candidate", "application__opening__designated_authority")
        .order_by("application__candidate__last_name", "application__candidate__first_name", "pk")
    )
    choices = []
    for row in rows:
        refusal = application_restore_refusal(row, by)
        reason = "" if refusal is None else choice_reason(refusal)
        choices.append(RestoreChoice(row.application, Stage(row.from_stage), reason))
    return choices


def choice_reason(refusal: PermissionDenied | ValidationError) -> str:
    """The restore checklist's short reason for ``refusal``."""
    if isinstance(refusal, PermissionDenied):
        return "Restoring to Offer needs offer authority"
    if refusal.code == ARCHIVED_CANDIDATE:
        return "Archived; unarchive first"
    return refusal.messages[0]


def application_restore_refusal(
    cancellation: StageChange, by: User
) -> PermissionDenied | ValidationError | None:
    """Return why ``by`` can't undo ``cancellation``, one of ``restorable_cancellations()``.

    The same rules as any move back to ``cancellation.from_stage``
    (``move_refusal``), so restoring into Offer still needs ``can_make_offer``,
    with a message that names the applicant. Returns None if they can.
    """
    application = cancellation.application
    refusal = move_refusal(application, cancellation.from_stage, by, expected_stage=Stage.REJECTED)
    if refusal is None:
        return None
    reason = str(refusal) if isinstance(refusal, PermissionDenied) else refusal.messages[0]
    message = (
        f"{application.candidate.full_name} can't be restored to "
        f"{Stage(cancellation.from_stage).label}. {reason}"
    )
    if isinstance(refusal, PermissionDenied):
        return PermissionDenied(message)
    return ValidationError(message, code=refusal.code)


@transaction.atomic
def restore_applications(
    opening: JobOpening, applications: Iterable[Application], *, by: User
) -> list[StageChange]:
    """Put each of ``applications`` back where it was before ``opening``'s latest closure.

    Each must be one of ``restorable_cancellations()``: cancelled at the latest
    closure and still at Rejected. It goes back to the stage its cancellation
    row moved it from, through ``move_application()`` with cause reopening, the
    note "Position reopened." and the closure it undoes, and its candidate is
    sent one "position reopened" email, keyed on that closure so it is never
    sent twice. Restoring into Offer still needs ``can_make_offer``, and
    archived candidates can't be restored.

    An empty ``applications`` records the choice to restore nobody. Either way
    one "Applicants restored" event is written, which is what takes the
    opening out of Needs attention.

    All or nothing: locks and re-reads the stored opening, checks
    ``restore_refusal()`` and every chosen application before any moves, and
    raises ``PermissionDenied`` or ``ValidationError`` (naming the applicant)
    on the first refusal, with nothing written. Returns the new history rows.
    """
    stored = (
        JobOpening.objects.select_for_update()
        .select_related("designated_authority")
        .get(pk=opening.pk)
    )
    refusal = restore_refusal(stored, by)
    if refusal is not None:
        raise refusal
    closure = latest_closure(stored)
    cancellations = {
        row.application_id: row
        for row in restorable_cancellations(stored).select_related(
            "application__candidate", "application__opening__designated_authority"
        )
    }
    chosen = []
    for application in sorted({*applications}, key=lambda application: application.pk):
        cancellation = cancellations.get(application.pk)
        if cancellation is None:
            raise ValidationError(
                f"{application.candidate.full_name} wasn't cancelled when {stored.title} last "
                "closed, or has moved since, so there's nothing to restore.",
                code=NOT_RESTORABLE,
            )
        refusal = application_restore_refusal(cancellation, by)
        if refusal is not None:
            raise refusal
        chosen.append(cancellation)
    rows = []
    occasion = closure_occasion(stored)
    for cancellation in chosen:
        application = cancellation.application
        rows.append(
            move_application(
                application,
                cancellation.from_stage,
                by=by,
                note=REOPEN_NOTE,
                cause=StageChange.Cause.REOPENING,
                expected_stage=Stage.REJECTED,
                closure=closure,
            )
        )
        send_candidate_message(application, CandidateMessage.Kind.RESTORED, occasion=occasion)
    OpeningEvent.objects.create(
        opening=stored,
        kind=OpeningEvent.Kind.APPLICATIONS_RESTORED,
        by=by,
        note=restore_note(chosen, left=len(cancellations) - len(chosen)),
    )
    return rows


def restore_note(chosen: list[StageChange], *, left: int) -> str:
    """The "Applicants restored" event's note: who went back to which stage, and who didn't."""
    if chosen:
        names = [
            f"{row.application.candidate.full_name} ({Stage(row.from_stage).label})"
            for row in chosen
        ]
        listed = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"
        note = f"Restored {listed}."
    else:
        note = "Chose not to restore anyone."
    if left:
        note += f" {left} applicant{'' if left == 1 else 's'} left cancelled."
    return note
