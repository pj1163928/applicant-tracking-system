"""Job openings: the roles staff hire for, each with a designated authority."""

from django.conf import settings
from django.db import models
from django.db.models import Case, IntegerField, Value, When
from django.urls import reverse

from openings.scopes import MINE, Scope


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
