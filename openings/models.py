"""Job openings (the roles staff hire for, each with a designated authority), their skills,
and their event history."""

from django.conf import settings
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import models
from django.db.models import (
    Case,
    Count,
    Exists,
    F,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Coalesce, Lower
from django.urls import reverse

from applications.stages import ACTIVE_STAGES
from openings.scopes import MINE, Scope

DUPLICATE_SKILL_NAME = "duplicate_skill_name"


class SkillQuerySet(models.QuerySet):
    def active(self) -> "SkillQuerySet":
        """Return the skills that may be attached to openings. Retired skills are left out."""
        return self.filter(is_active=True)

    def retired(self) -> "SkillQuerySet":
        """Return the retired skills, which openings keep but can't newly attach."""
        return self.filter(is_active=False)

    def named(self, name: str) -> "SkillQuerySet":
        """Return the skill called ``name``, ignoring capitals, as the database compares names."""
        return self.annotate(_lower_name=Lower("name")).filter(_lower_name=name.lower())


class Skill(models.Model):
    """A qualification an opening asks for, such as Python. Shared by every opening that lists it.

    Skills are never deleted: they are retired (``is_active=False``) so openings
    that already list them keep them, while no opening can newly attach them.
    """

    name = models.CharField(max_length=60)
    is_active = models.BooleanField(default=True)

    objects = SkillQuerySet.as_manager()

    class Meta:
        ordering = [Lower("name"), "pk"]
        constraints = [
            # Names keep the capitals they were typed with; only uniqueness ignores case.
            models.UniqueConstraint(
                Lower("name"),
                name="skill_name_unique_ignoring_case",
                violation_error_message="A skill with this name already exists.",
                violation_error_code=DUPLICATE_SKILL_NAME,
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def validate_constraints(self, exclude=None) -> None:
        # Django reports a clash on Lower("name") against the whole form; put it on the name field.
        try:
            super().validate_constraints(exclude=exclude)
        except ValidationError as error:
            errors = error.update_error_dict({})
            general = errors.pop(NON_FIELD_ERRORS, [])
            for item in general:
                key = "name" if item.code == DUPLICATE_SKILL_NAME else NON_FIELD_ERRORS
                errors.setdefault(key, []).append(item)
            raise ValidationError(errors) from None

    def retire(self) -> None:
        """Stop openings from newly attaching this skill. Openings that list it keep it."""
        if self.is_active:
            self.is_active = False
            self.save(update_fields=["is_active"])

    def reactivate(self) -> None:
        """Let openings attach a retired skill again."""
        if not self.is_active:
            self.is_active = True
            self.save(update_fields=["is_active"])


class OpeningStatus(models.TextChoices):
    """Whether an opening takes new applications. Also reachable as ``JobOpening.Status``."""

    OPEN = "open", "Open"
    CLOSED = "closed", "Closed"


class GraceExpiryAction(models.TextChoices):
    """What happens when a grace period ends. Also reachable as ``JobOpening.GraceExpiryAction``."""

    AUTO_CANCEL = "auto_cancel", "Cancel the remaining applications"
    FLAG_OVERDUE = "flag_overdue", "Flag the opening as overdue"


class JobOpeningQuerySet(models.QuerySet):
    def in_scope(self, scope: Scope, user) -> "JobOpeningQuerySet":
        """Return the openings a list scope shows: ``MINE`` is the user's own, ``ALL`` is every one.

        "Mine" means the user is the designated authority. It only narrows a
        list; every opening stays reachable through ``ALL`` and by its URL.
        """
        if scope == MINE:
            return self.filter(designated_authority=user)
        return self

    def accepting_applications(self) -> "JobOpeningQuerySet":
        """Return the openings that take new applications: the open ones."""
        return self.filter(status=OpeningStatus.OPEN)

    def with_active_count(self) -> "JobOpeningQuerySet":
        """Annotate each opening with ``active_count``: its applications at an active stage."""
        return self.annotate(
            active_count=Count("applications", filter=Q(applications__stage__in=ACTIVE_STAGES))
        )

    def closed_with_active_applications(self) -> "JobOpeningQuerySet":
        """Return the closed openings with at least one application at an active stage.

        Each is annotated with ``active_count``. An opening leaves this set as
        soon as nobody is in progress; the Admin in-progress view lists it.
        """
        return (
            self.filter(status=OpeningStatus.CLOSED).with_active_count().filter(active_count__gt=0)
        )

    def awaiting_closure_decision(self) -> "JobOpeningQuerySet":
        """Return the closed openings with active applications and no grace period running.

        Each is annotated with ``active_count``. Someone allowed by
        ``accounts.permissions.can_decide_closure`` must decide what happens to
        those applicants; until then the opening shows in the Needs attention
        panel. That includes overdue openings (a grace period that ended), but
        not ones whose grace period is still running.
        """
        return self.filter(
            Q(grace_period_ends__isnull=True) | Q(grace_expired_on__isnull=False)
        ).closed_with_active_applications()

    def with_grace_period_running(self) -> "JobOpeningQuerySet":
        """Return the closed openings whose grace period ``process_grace_periods`` hasn't ended."""
        return self.filter(
            status=OpeningStatus.CLOSED,
            grace_period_ends__isnull=False,
            grace_expired_on__isnull=True,
        )

    def awaiting_restore_choice(self) -> "JobOpeningQuerySet":
        """Return the reopened openings where someone must still choose which applicants to restore.

        That is an open opening reopened since its latest closure, with no
        "Applicants restored" event since that reopening, and at least one
        application the latest closure cancelled that is still at Rejected
        because of it. Each is annotated with ``restorable_count``, archived
        candidates included (they are listed, but must be unarchived first).
        """
        from applications.models import StageChange  # applications.models imports this module

        def latest(kind: str) -> Subquery:
            events = OpeningEvent.objects.filter(opening=OuterRef("pk"), kind=kind)
            return Subquery(events.order_by("-pk").values("pk")[:1])

        restorable = (
            StageChange.objects.cancellations_to_restore()
            .filter(closure=OuterRef("_latest_closed"))
            .order_by()
            .values("closure")
            .annotate(count=Count("pk"))
            .values("count")
        )
        restored_since = OpeningEvent.objects.filter(
            opening=OuterRef("pk"),
            kind=OpeningEventKind.APPLICATIONS_RESTORED,
            pk__gt=OuterRef("_latest_reopened"),
        )
        return (
            self.filter(status=OpeningStatus.OPEN)
            .annotate(
                _latest_closed=latest(OpeningEventKind.CLOSED),
                _latest_reopened=latest(OpeningEventKind.REOPENED),
            )
            .filter(_latest_reopened__gt=F("_latest_closed"))
            .exclude(Exists(restored_since))
            .annotate(restorable_count=Coalesce(Subquery(restorable), 0))
            .filter(restorable_count__gt=0)
        )

    def open_first(self) -> "JobOpeningQuerySet":
        """Order open openings before closed ones, then by title."""
        return self.annotate(
            _closed=Case(
                When(status=OpeningStatus.OPEN, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by("_closed", "title", "pk")


class JobOpening(models.Model):
    """A position the company is hiring for.

    Every opening has a designated authority: the staff member responsible for
    its offer and closure decisions. Who may be picked is
    ``accounts.permissions.eligible_authorities()``.
    """

    Status = OpeningStatus
    GraceExpiryAction = GraceExpiryAction

    title = models.CharField(max_length=150)
    department = models.CharField(max_length=100)
    location = models.CharField(max_length=100, blank=True)
    description = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    designated_authority = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="authority_openings",
    )
    skills = models.ManyToManyField(Skill, through="OpeningSkill", related_name="openings")
    # A closed opening's grace period, in calendar days of the project time zone. Set and
    # extended only through openings.services; process_grace_periods sets grace_expired_on
    # when it handles the end, which is what makes the end-of-period action run only once.
    grace_period_ends = models.DateField(null=True, blank=True)
    grace_expiry_action = models.CharField(
        max_length=20, choices=GraceExpiryAction.choices, blank=True
    )
    grace_period_set_on = models.DateField(null=True, blank=True)
    grace_expired_on = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = JobOpeningQuerySet.as_manager()

    class Meta:
        ordering = ["title", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=OpeningStatus.values),
                name="opening_status_valid",
            ),
            # The grace period's end, action and start are filled in or empty together,
            # and it can only have ended if there is one.
            models.CheckConstraint(
                condition=(
                    models.Q(
                        grace_period_ends__isnull=True,
                        grace_expiry_action="",
                        grace_period_set_on__isnull=True,
                        grace_expired_on__isnull=True,
                    )
                    | models.Q(
                        grace_period_ends__isnull=False,
                        grace_expiry_action__in=GraceExpiryAction.values,
                        grace_period_set_on__isnull=False,
                    )
                ),
                name="opening_grace_period_complete",
            ),
        ]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("openings:detail", args=[self.pk])

    @property
    def is_open(self) -> bool:
        return self.status == self.Status.OPEN

    @property
    def has_grace_period(self) -> bool:
        return self.grace_period_ends is not None

    @property
    def grace_period_running(self) -> bool:
        """True while a grace period is set and ``process_grace_periods`` hasn't ended it."""
        return self.has_grace_period and self.grace_expired_on is None

    @property
    def is_overdue(self) -> bool:
        """True once a flag-overdue grace period has ended (until it is extended)."""
        return (
            self.grace_expired_on is not None
            and self.grace_expiry_action == GraceExpiryAction.FLAG_OVERDUE
        )

    @property
    def auto_cancelled(self) -> bool:
        """True once an auto-cancel grace period has ended. It can't be extended after that."""
        return (
            self.grace_expired_on is not None
            and self.grace_expiry_action == GraceExpiryAction.AUTO_CANCEL
        )


class OpeningSkill(models.Model):
    """One skill listed on one opening. A skill on any opening can't be deleted (PROTECT)."""

    opening = models.ForeignKey(JobOpening, on_delete=models.CASCADE)
    skill = models.ForeignKey(Skill, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["opening", "skill"], name="opening_skill_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.skill} on {self.opening}"


class OpeningEventKind(models.TextChoices):
    """What happened to an opening. Also reachable as ``OpeningEvent.Kind``."""

    CLOSED = "closed", "Closed"
    APPLICATIONS_CANCELLED = "applications_cancelled", "Remaining applications cancelled"
    GRACE_PERIOD_SET = "grace_period_set", "Grace period set"
    GRACE_PERIOD_EXTENDED = "grace_period_extended", "Grace period extended"
    GRACE_PERIOD_EXPIRED = "grace_period_expired", "Grace period ended"
    REOPENED = "reopened", "Reopened"
    APPLICATIONS_RESTORED = "applications_restored", "Applicants restored"


class OpeningEvent(models.Model):
    """One row of an opening's permanent event history: what happened, who did it, when, and why.

    Written only by the closure services in ``openings.services``, never edited.
    """

    Kind = OpeningEventKind

    opening = models.ForeignKey(JobOpening, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=30, choices=Kind.choices)
    by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="opening_events"
    )
    at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind__in=OpeningEventKind.values),
                name="opening_event_kind_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.opening}"
