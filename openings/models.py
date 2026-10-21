"""Job openings (the roles staff hire for, each with a designated authority) and their skills."""

from django.conf import settings
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import models
from django.db.models import Case, IntegerField, Value, When
from django.db.models.functions import Lower
from django.urls import reverse

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
        ]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("openings:detail", args=[self.pk])

    @property
    def is_open(self) -> bool:
        return self.status == self.Status.OPEN


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
