"""Recording applications: who may apply where, the source pre-fill, and the atomic create.

``record_application()`` is the only way an application is created. It writes
the application and its first ``StageChange`` row (no stage → Applied) in one
transaction, so neither can exist without the other.
"""

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import QuerySet

from accounts.permissions import can_manage_applications
from applications.models import Application, StageChange
from applications.stages import Stage
from candidates.models import Candidate, Source
from openings.models import JobOpening

CLOSED_OPENING = "closed_opening"
DUPLICATE_APPLICATION = "duplicate_application"
RETIRED_SOURCE = "retired_source"


def application_refusal(candidate: Candidate, opening: JobOpening) -> ValidationError | None:
    """Return why ``candidate`` can't apply for ``opening`` now, or None if they can.

    The form shows this error and ``record_application()`` raises it, so the
    rule lives in one place. Later phases add more reasons (archived candidates).
    """
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
    """
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
    ``ValidationError`` if the opening is closed, the candidate has already
    applied for it, or the source is retired.
    """
    if not can_manage_applications(by):
        raise PermissionDenied("Only Recruiters and Admins can record applications.")
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


def duplicate_error(candidate: Candidate, opening: JobOpening) -> ValidationError:
    """The friendly error for a second application by the same candidate for the same opening."""
    return ValidationError(
        f"{candidate.full_name} has already applied for {opening.title}.",
        code=DUPLICATE_APPLICATION,
    )
