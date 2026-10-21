"""Emails: the candidate messaging service, and the staff notices about closed openings.

Every email is sent only once the database transaction that caused it commits
(``transaction.on_commit``), so a change that is rolled back never emails
anyone. Tests run those callbacks with ``django_capture_on_commit_callbacks``.
"""

from django.contrib.auth.models import User
from django.core.mail import EmailMessage
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string

from applications.models import Application
from notifications.models import CandidateMessage
from openings.models import JobOpening


def render_email(name: str, context: dict) -> tuple[str, str]:
    """Return the (subject, body) of the email ``name``, from ``notifications/email/``."""
    subject = render_to_string(f"notifications/email/{name}_subject.txt", context)
    body = render_to_string(f"notifications/email/{name}_body.txt", context)
    return " ".join(subject.split()), body.strip() + "\n"


def send_after_commit(subject: str, body: str, to: str) -> None:
    """Send one plain-text email to ``to`` once the current transaction commits."""
    transaction.on_commit(lambda: EmailMessage(subject, body, to=[to]).send())


def notify_authority_of_closure(
    opening: JobOpening, *, active_count: int, by: User, note: str = ""
) -> bool:
    """Email ``opening``'s designated authority that it closed with applicants still in progress.

    Returns False, and sends nothing, if the authority has no email address.
    """
    authority = opening.designated_authority
    if not authority.email:
        return False
    subject, body = render_email(
        "closure_awaiting_decision",
        {
            "opening": opening,
            "authority": authority,
            "active_count": active_count,
            "closed_by": by.get_full_name() or by.username,
            "note": note,
        },
    )
    send_after_commit(subject, body, authority.email)
    return True


def send_candidate_message(
    application: Application, kind: str, *, occasion: str
) -> CandidateMessage | None:
    """Build, log and send one email to ``application``'s candidate, unless it was already sent.

    A message is identified by (application, ``kind``, ``occasion``); the
    occasion names what it is about, such as one closure of the opening. The
    subject and body come from the ``notifications/email/<kind>_*.txt``
    templates. The ``CandidateMessage`` row is written in the caller's
    transaction and the email goes out once it commits, so a rolled-back
    change sends nothing. Returns the new row, or None if this message was
    already sent; the database's unique constraint backs that up when two
    requests race.
    """
    identity = {"application": application, "kind": kind, "occasion": occasion}
    if CandidateMessage.objects.filter(**identity).exists():
        return None
    candidate = application.candidate
    subject, body = render_email(
        kind, {"application": application, "candidate": candidate, "opening": application.opening}
    )
    try:
        with transaction.atomic():
            message = CandidateMessage.objects.create(
                candidate=candidate, subject=subject, body=body, **identity
            )
    except IntegrityError:
        # Another request logged the same message first; anything else is a real error.
        if CandidateMessage.objects.filter(**identity).exists():
            return None
        raise
    send_after_commit(subject, body, candidate.email)
    return message
