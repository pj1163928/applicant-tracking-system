"""A candidate's lifecycle: archiving, unarchiving and permanent deletion.

Each function checks its permission rule on the server, so a hand-made POST
from someone without the right is refused even though the page hides the
action.
"""

from dataclasses import dataclass

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone

from accounts.permissions import can_delete_candidates, can_manage_candidates
from applications.models import Application, StageChange
from applications.stages import ACTIVE_STAGES
from candidates.models import Candidate
from notifications.models import CandidateMessage

ACTIVE_APPLICATION = "active_application"


def require_candidate_manager(by: User) -> None:
    """Raise ``PermissionDenied`` unless ``by`` may archive and unarchive candidates."""
    if not can_manage_candidates(by):
        raise PermissionDenied("Only Recruiters and Admins can archive or unarchive candidates.")


def archive_refusal(candidate: Candidate) -> ValidationError | None:
    """Return why ``candidate`` can't be archived now, or None if they can.

    A candidate with any application at an active stage (Applied through
    Offer) is still in progress. Hired, Rejected and Withdrawn applications
    never block archiving.
    """
    if candidate.applications.filter(stage__in=ACTIVE_STAGES).exists():
        return ValidationError(
            f"{candidate.full_name} has an active application, so they can't be archived. "
            "Move it to Hired, Rejected or Withdrawn first.",
            code=ACTIVE_APPLICATION,
        )
    return None


@transaction.atomic
def archive_candidate(candidate: Candidate, *, by: User) -> None:
    """Archive ``candidate``: they leave the everyday list and can't apply for anything.

    Their applications are kept, and still show on pipeline boards. Locks and
    re-reads the stored candidate first; archiving an archived candidate
    changes nothing. Raises ``PermissionDenied`` unless ``by`` may manage
    candidates, and ``ValidationError`` while any of their applications is active.
    """
    require_candidate_manager(by)
    stored = Candidate.objects.select_for_update().get(pk=candidate.pk)
    refusal = archive_refusal(stored)
    if refusal is not None:
        raise refusal
    if not stored.is_archived:
        stored.is_archived, stored.archived_at = True, timezone.now()
        stored.save(update_fields=["is_archived", "archived_at", "updated_at"])
    candidate.is_archived, candidate.archived_at = stored.is_archived, stored.archived_at


@transaction.atomic
def unarchive_candidate(candidate: Candidate, *, by: User) -> None:
    """Bring an archived ``candidate`` back to the everyday list, able to apply again.

    Clears ``archived_at`` too. Unarchiving a candidate who isn't archived
    changes nothing. Raises ``PermissionDenied`` unless ``by`` may manage candidates.
    """
    require_candidate_manager(by)
    stored = Candidate.objects.select_for_update().get(pk=candidate.pk)
    if stored.is_archived:
        stored.is_archived, stored.archived_at = False, None
        stored.save(update_fields=["is_archived", "archived_at", "updated_at"])
    candidate.is_archived, candidate.archived_at = False, None


@dataclass(frozen=True)
class DeletionSummary:
    """Everything a permanent delete of one candidate would destroy, for the confirmation page.

    Each application's ``history`` holds its stage changes, newest first, as
    ``applications/partials/history_list.html`` shows them. ``messages`` are
    every email logged as sent to the candidate, newest first.
    """

    applications: list[Application]
    messages: list[CandidateMessage]

    @property
    def stage_change_count(self) -> int:
        return sum(len(application.history) for application in self.applications)


def deletion_summary(candidate: Candidate) -> DeletionSummary:
    """Return what deleting ``candidate`` would destroy: every application, its history,
    and every message sent to them."""
    history = Prefetch(
        "stage_changes",
        queryset=StageChange.objects.select_related("changed_by").order_by("-changed_at", "-pk"),
        to_attr="history",
    )
    applications = (
        candidate.applications.newest_first()
        .select_related("opening", "source")
        .prefetch_related(history)
    )
    messages = candidate.messages.select_related("application__opening")
    return DeletionSummary(applications=list(applications), messages=list(messages))


@transaction.atomic
def delete_candidate(candidate: Candidate, *, by: User) -> None:
    """Permanently delete ``candidate`` with all their applications, stage history and messages.

    This can't be undone. Raises ``PermissionDenied`` unless ``by`` is an
    active Admin; nothing is deleted when it refuses.
    """
    if not can_delete_candidates(by):
        raise PermissionDenied("Only Admins can permanently delete candidates.")
    candidate.delete()
