"""Recording applications and moving them between stages.

``record_application()`` is the only way an application is created. It writes
the application and its first ``StageChange`` row (no stage → Applied) in one
transaction, so neither can exist without the other.

``move_application()`` is the only way an application's stage changes. It
checks the stage rules and permissions, then writes one ``StageChange`` row and
updates the cached stage in one transaction.
"""

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import QuerySet

from accounts.permissions import can_make_offer, can_manage_applications, can_move_applications
from applications.models import Application, StageChange
from applications.stages import (
    BACK,
    OFFER_STAGES,
    REOPEN,
    SKIP,
    Stage,
    can_move,
    move_kind,
    requires_note,
)
from candidates.models import Candidate, Source
from openings.models import JobOpening, OpeningEvent

ARCHIVED_CANDIDATE = "archived_candidate"
CLOSED_OPENING = "closed_opening"
DUPLICATE_APPLICATION = "duplicate_application"
RETIRED_SOURCE = "retired_source"


def application_refusal(candidate: Candidate, opening: JobOpening) -> ValidationError | None:
    """Return why ``candidate`` can't apply for ``opening`` now, or None if they can.

    The form shows this error and ``record_application()`` raises it, so the
    rule lives in one place. Archived candidates can't apply for anything,
    closed openings take no new applications, and nobody applies twice.
    Judges ``candidate`` as given, so ``record_application()`` passes the stored row.
    """
    if candidate.is_archived:
        return ValidationError(
            f"{candidate.full_name} is archived, so they can't apply for anything. "
            "Unarchive them first.",
            code=ARCHIVED_CANDIDATE,
        )
    if not opening.is_open:
        return ValidationError(
            f"{opening.title} is closed, so it can't take new applications.",
            code=CLOSED_OPENING,
        )
    if Application.objects.filter(candidate=candidate, opening=opening).exists():
        return duplicate_error(candidate, opening)
    return None


def openings_open_to(candidate: Candidate) -> QuerySet[JobOpening]:
    """Return the openings ``candidate`` could apply for now: open, and not applied for yet.

    Pages show the "Record application" action only when this is not empty.
    An archived candidate can't apply for anything, so gets none.
    """
    if candidate.is_archived:
        return JobOpening.objects.none()
    return JobOpening.objects.accepting_applications().exclude(applications__candidate=candidate)


def prefill_source(candidate: Candidate) -> Source | None:
    """Return the source to pre-fill for ``candidate``'s next application, or None.

    That is the source of their most recently recorded application, if it is
    still active. A retired source is never pre-filled, since new applications
    can't pick it.
    """
    latest = candidate.applications.newest_first().select_related("source").first()
    if latest is None or not latest.source.is_active:
        return None
    return latest.source


@transaction.atomic
def record_application(
    *,
    candidate: Candidate,
    opening: JobOpening,
    source: Source,
    by: User,
    referred_by: str = "",
) -> Application:
    """Record that ``candidate`` applied for ``opening`` through ``source``, at Applied.

    Writes the application and its first history row (no stage → Applied,
    cause manual, by ``by``) in one transaction: if either write fails, neither
    is kept. ``referred_by`` is kept only for Referral sources.

    Raises ``PermissionDenied`` unless ``by`` may manage applications, and
    ``ValidationError`` if the candidate is archived, the opening is closed,
    the candidate has already applied for it, or the source is retired.
    """
    if not can_manage_applications(by):
        raise PermissionDenied("Only Recruiters and Admins can record applications.")
    # Lock and re-read the candidate, so one archived since the caller loaded it is refused.
    candidate = Candidate.objects.select_for_update().get(pk=candidate.pk)
    refusal = application_refusal(candidate, opening)
    if refusal is not None:
        raise refusal
    if not source.is_active:
        raise ValidationError(
            f"{source.name} is retired, so new applications can't pick it.", code=RETIRED_SOURCE
        )
    try:
        with transaction.atomic():
            application = Application.objects.create(
                candidate=candidate,
                opening=opening,
                source=source,
                referred_by=referred_by,
                stage=Stage.APPLIED,
            )
    except IntegrityError:
        # Another request recorded the same application first; anything else is a real error.
        if Application.objects.filter(candidate=candidate, opening=opening).exists():
            raise duplicate_error(candidate, opening) from None
        raise
    StageChange.objects.create(
        application=application,
        from_stage="",
        to_stage=Stage.APPLIED,
        changed_by=by,
        cause=StageChange.Cause.MANUAL,
    )
    return application


ILLEGAL_MOVE = "illegal_move"
NOTE_REQUIRED = "note_required"
STALE_STAGE = "stale_stage"

NOTE_REASONS = {SKIP: "is skipping ahead", BACK: "is moving back", REOPEN: "is being reopened"}


def move_refusal(
    application: Application, to_stage: str, by: User, *, expected_stage: str | None = None
) -> ValidationError | PermissionDenied | None:
    """Return why ``by`` can't move ``application`` to ``to_stage`` now, or None if they can.

    Checks, in order: that ``by`` may move stages at all; that the application
    is still at ``expected_stage`` (the stage the user's card showed), if one is
    given; that the candidate isn't archived; the transitions table; and
    ``can_make_offer`` for Offer and Hired.
    The note is not checked here: the board asks for it after this passes, and
    ``move_application()`` refuses a missing one. Judges ``application.stage``
    as given, so ``move_application()`` passes the stored row.
    """
    if not can_move_applications(by):
        return PermissionDenied("Only Admins, Recruiters and Hiring Managers can move applicants.")
    name, current = application.candidate.full_name, application.stage
    if expected_stage is not None and current != expected_stage:
        return ValidationError(
            f"{name} has moved to {Stage(current).label} since this board loaded, "
            "so that move wasn't made. The board now shows where they are.",
            code=STALE_STAGE,
        )
    if application.candidate.is_archived:
        # An archived candidate has no active applications; reopening one would undo that.
        return ValidationError(
            f"{name} is archived, so their applications can't be moved. Unarchive them first.",
            code=ARCHIVED_CANDIDATE,
        )
    if not can_move(current, to_stage):
        return ValidationError(illegal_move_message(name, current, to_stage), code=ILLEGAL_MOVE)
    if to_stage in OFFER_STAGES and not can_make_offer(by, application.opening):
        authority = application.opening.designated_authority
        return PermissionDenied(
            f"Only Admins, Hiring Managers or {authority.get_full_name() or authority.username}, "
            f"this opening's designated authority, can move applicants into "
            f"{Stage(to_stage).label}."
        )
    return None


def illegal_move_message(name: str, from_stage: str, to_stage: str) -> str:
    """Explain, in words for staff, why the transitions table refuses this move."""
    if to_stage not in Stage.values:
        return f"{to_stage!r} isn't a hiring stage."
    current, target = Stage(from_stage).label, Stage(to_stage).label
    if from_stage == to_stage:
        return f"{name} is already at {current}."
    if from_stage == Stage.HIRED:
        return f"{name} has been hired, and Hired is final."
    if to_stage == Stage.HIRED:
        return f"{name} can only be moved to Hired from Offer."
    return f"A {current.lower()} application can only be reopened to an active stage, not {target}."


@transaction.atomic
def move_application(
    application: Application,
    to_stage: str,
    *,
    by: User,
    note: str = "",
    cause: str = StageChange.Cause.MANUAL,
    expected_stage: str | None = None,
    closure: OpeningEvent | None = None,
) -> StageChange:
    """Move ``application`` to ``to_stage``: the only way an application's stage changes.

    Locks and re-reads the stored application, so the rules judge its real
    stage, not the caller's possibly out-of-date copy. Then writes one
    ``StageChange`` row (from, to, ``by``, now, the trimmed ``note``, ``cause``)
    and updates the cached stage in the same transaction: if either write
    fails, neither is kept. Returns the new row and updates ``application``.

    Pass ``expected_stage`` (the stage the user's card showed) to refuse the
    move if anyone has moved the application since, so a stale card or a
    repeated submission can't overwrite a newer stage.

    ``closure`` is the opening's "closed" event that a cancellation (cause
    closure) or a restore (cause reopening) belongs to; manual moves have none.

    Raises ``PermissionDenied`` if ``by`` may not move stages, or may not move
    into Offer or Hired here, and ``ValidationError`` (code ``STALE_STAGE``,
    ``ARCHIVED_CANDIDATE``, ``ILLEGAL_MOVE`` or ``NOTE_REQUIRED``) for the rest. Nothing is written
    when it refuses.
    """
    stored = (
        Application.objects.select_for_update()
        .select_related("candidate", "opening__designated_authority")
        .get(pk=application.pk)
    )
    refusal = move_refusal(stored, to_stage, by, expected_stage=expected_stage)
    if refusal is not None:
        raise refusal
    note = note.strip()
    if requires_note(stored.stage, to_stage) and not note:
        reason = NOTE_REASONS[move_kind(stored.stage, to_stage)]
        raise ValidationError(
            f"Add a note to say why {stored.candidate.full_name} {reason} "
            f"to {Stage(to_stage).label}.",
            code=NOTE_REQUIRED,
        )
    row = StageChange.objects.create(
        application=stored,
        from_stage=stored.stage,
        to_stage=to_stage,
        changed_by=by,
        note=note,
        cause=cause,
        closure=closure,
    )
    stored.stage = to_stage
    stored.save(update_fields=["stage", "updated_at"])
    application.stage, application.updated_at = stored.stage, stored.updated_at
    return row


def duplicate_error(candidate: Candidate, opening: JobOpening) -> ValidationError:
    """The friendly error for a second application by the same candidate for the same opening."""
    return ValidationError(
        f"{candidate.full_name} has already applied for {opening.title}.",
        code=DUPLICATE_APPLICATION,
    )
