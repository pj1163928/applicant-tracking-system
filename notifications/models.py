"""The log of every email sent to a candidate, which also stops the same email going out twice."""

from django.db import models

from applications.models import Application
from candidates.models import Candidate


class CandidateMessageKind(models.TextChoices):
    """Which email a candidate was sent. Also reachable as ``CandidateMessage.Kind``."""

    CANCELLED = "cancelled", "Application cancelled: position closed"
    GRACE_PERIOD_SET = "grace_period_set", "Grace period set"
    GRACE_REMINDER = "grace_reminder", "Grace period reminder"
    RESTORED = "restored", "Application restored: position reopened"


class CandidateMessage(models.Model):
    """One email sent to a candidate about one application, exactly as it was sent.

    A message's identity is (application, kind, occasion). The occasion names
    what the email is about, such as one closure of the opening, so the database
    refuses a second copy of the same email. Write these only through
    ``notifications.services.send_candidate_message()``.
    """

    Kind = CandidateMessageKind

    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="messages")
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="messages")
    kind = models.CharField(max_length=30, choices=Kind.choices)
    occasion = models.CharField(max_length=100)
    subject = models.CharField(max_length=200)
    body = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["application", "kind", "occasion"],
                name="candidate_message_sent_once",
            ),
            models.CheckConstraint(
                condition=models.Q(kind__in=CandidateMessageKind.values),
                name="candidate_message_kind_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.subject} → {self.candidate}"
