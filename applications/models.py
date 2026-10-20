"""Applications (a candidate applying for one opening) and their permanent stage history."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from applications.stages import Stage
from candidates.models import Candidate, Source
from openings.models import JobOpening


class StageChangeCause(models.TextChoices):
    """Why a stage changed. Also reachable as ``StageChange.Cause``."""

    MANUAL = "manual", "Manual"
    CLOSURE = "closure", "Closure"


class ApplicationQuerySet(models.QuerySet):
    def newest_first(self) -> "ApplicationQuerySet":
        """Order the most recently recorded applications first, newest pk breaking ties."""
        return self.order_by("-created_at", "-pk")


class Application(models.Model):
    """One candidate's application for one opening, through one source.

    ``stage`` is a cache of the latest ``StageChange`` row. Create applications
    with ``applications.services.record_application()``, which writes the first
    history row in the same transaction.
    """

    Stage = Stage

    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="applications")
    opening = models.ForeignKey(JobOpening, on_delete=models.PROTECT, related_name="applications")
    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="applications")
    referred_by = models.CharField(max_length=150, blank=True)
    stage = models.CharField(max_length=20, choices=Stage.choices, default=Stage.APPLIED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ApplicationQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["candidate", "opening"],
                name="application_once_per_candidate_and_opening",
                violation_error_message="This candidate has already applied for this opening.",
            ),
            models.CheckConstraint(
                condition=Q(stage__in=Stage.values),
                name="application_stage_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.candidate} for {self.opening}"

    def save(self, *args, **kwargs) -> None:
        # "Referred by" belongs only to Referral sources. Clearing it here covers
        # every save, from a form or from code, so stale text is never kept.
        self.referred_by = self.referred_by.strip()
        if self.referred_by and self.source.category != Source.Category.REFERRAL:
            self.referred_by = ""
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = {*update_fields, "referred_by"}
        super().save(*args, **kwargs)

    @property
    def shows_referred_by(self) -> bool:
        """True when the source is a Referral, so "referred by" applies."""
        return self.source.category == Source.Category.REFERRAL


class StageChange(models.Model):
    """One row of an application's permanent history: from, to, who, when, note and cause.

    The first row of every application has an empty ``from_stage`` and
    ``to_stage`` Applied; the database allows only one such row per application.
    """

    Cause = StageChangeCause

    application = models.ForeignKey(
        Application, on_delete=models.CASCADE, related_name="stage_changes"
    )
    from_stage = models.CharField(max_length=20, choices=Stage.choices, blank=True)
    to_stage = models.CharField(max_length=20, choices=Stage.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="stage_changes"
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True)
    cause = models.CharField(max_length=10, choices=Cause.choices, default=Cause.MANUAL)

    class Meta:
        ordering = ["changed_at", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(from_stage__in=[*Stage.values, ""]),
                name="stage_change_from_stage_valid",
            ),
            models.CheckConstraint(
                condition=Q(to_stage__in=Stage.values),
                name="stage_change_to_stage_valid",
            ),
            models.CheckConstraint(
                condition=Q(cause__in=StageChangeCause.values),
                name="stage_change_cause_valid",
            ),
            models.CheckConstraint(
                condition=~Q(from_stage=models.F("to_stage")),
                name="stage_change_changes_the_stage",
            ),
            models.UniqueConstraint(
                fields=["application"],
                condition=Q(from_stage=""),
                name="stage_change_one_initial_row_per_application",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.from_stage or '—'} → {self.to_stage}"
