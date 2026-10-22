"""Staff departure: deactivating someone after handing each of their openings to someone else.

``deactivate_staff()`` is the only way a staff account is deactivated; the
Django admin shows ``is_active`` read-only so this flow can't be bypassed.
"""

from collections.abc import Mapping

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from accounts.permissions import can_be_designated_authority, can_manage_staff
from openings.models import JobOpening, OpeningEvent
from openings.services import INELIGIBLE_AUTHORITY, change_authority, display_name

ALREADY_INACTIVE = "already_inactive"
SELF_DEACTIVATION = "self_deactivation"
MISSING_REASSIGNMENT = "missing_reassignment"
UNEXPECTED_REASSIGNMENT = "unexpected_reassignment"


def responsible_openings(user: User):
    """Return the openings ``user`` is the designated authority of, open and closed, by title."""
    return JobOpening.objects.filter(designated_authority=user).order_by("title", "pk")


def listed(titles: list[str]) -> str:
    """``titles`` joined for a sentence: "A", "A and B", "A, B and C"."""
    return titles[0] if len(titles) == 1 else f"{', '.join(titles[:-1])} and {titles[-1]}"


def deactivate_refusal(
    user: User,
    openings: list[JobOpening],
    new_authorities: Mapping[int, User | None],
    *,
    by: User,
) -> PermissionDenied | ValidationError | None:
    """Return why ``by`` can't deactivate ``user`` with these reassignments, or None if they can.

    ``openings`` are the ones ``user`` is responsible for, and
    ``new_authorities`` maps each reassigned opening's pk to its new authority
    as stored now (None if that user no longer exists). Only Admins may
    (``can_manage_staff``), never on their own account or on one already
    inactive. Every one of ``openings``, and nothing else, must get a new
    authority who is eligible (``can_be_designated_authority``) and isn't
    ``user``. Checked here, whatever the form offered.
    """
    if not can_manage_staff(by):
        return PermissionDenied("Only Admins can deactivate staff.")
    if user.pk == by.pk:
        return ValidationError("You can't deactivate your own account.", code=SELF_DEACTIVATION)
    if not user.is_active:
        return ValidationError(
            f"{display_name(user)} is already deactivated.", code=ALREADY_INACTIVE
        )
    owned = {opening.pk for opening in openings}
    missing = [opening.title for opening in openings if opening.pk not in new_authorities]
    if missing:
        return ValidationError(
            f"Pick a new designated authority for {listed(missing)} before deactivating "
            f"{display_name(user)}.",
            code=MISSING_REASSIGNMENT,
        )
    if new_authorities.keys() - owned:
        return ValidationError(
            f"Only openings {display_name(user)} is responsible for can be reassigned here.",
            code=UNEXPECTED_REASSIGNMENT,
        )
    for opening in openings:
        to = new_authorities[opening.pk]
        if to is None or to.pk == user.pk or not can_be_designated_authority(to):
            who = "That person" if to is None else display_name(to)
            return ValidationError(
                f"{who} can't take over {opening.title}. Pick an active Admin, Recruiter or "
                f"Hiring Manager other than {display_name(user)}.",
                code=INELIGIBLE_AUTHORITY,
            )
    return None


@transaction.atomic
def deactivate_staff(
    user: User, reassignments: Mapping[JobOpening, User], *, by: User
) -> list[OpeningEvent]:
    """Hand each of ``user``'s openings to its new authority, then deactivate ``user``.

    ``reassignments`` maps every opening ``user`` is the designated authority
    of (open and closed) to the person taking it over. Each goes through
    ``change_authority()``, which writes an "authority changed" event and
    emails the new authority. Then ``user`` can no longer log in, and drops
    out of every list of authority choices.

    All or nothing, in one transaction: locks and re-reads ``user``, their
    openings and the new authorities, then checks ``deactivate_refusal()``
    before writing anything. Raises ``PermissionDenied`` unless ``by`` is an
    Admin, and ``ValidationError`` if any opening is left without an eligible
    new authority (or for anything else it refuses). If any write fails,
    every reassignment, event and the deactivation are rolled back, and the
    emails, which go out only once the transaction commits, are never sent.
    Returns the new events.
    """
    stored = User.objects.select_for_update().get(pk=user.pk)
    openings = list(responsible_openings(stored).select_for_update())
    found = User.objects.select_for_update().in_bulk([to.pk for to in reassignments.values()])
    new_authorities = {opening.pk: found.get(to.pk) for opening, to in reassignments.items()}
    refusal = deactivate_refusal(stored, openings, new_authorities, by=by)
    if refusal is not None:
        raise refusal
    note = f"{display_name(stored)} is leaving, so their openings were handed over."
    events = [
        change_authority(opening, to=new_authorities[opening.pk], by=by, note=note)
        for opening in openings
    ]
    stored.is_active = False
    stored.save(update_fields=["is_active"])
    user.is_active = False
    return events
