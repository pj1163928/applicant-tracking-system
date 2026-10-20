"""Candidates (the people staff track, who never log in) and the sources they apply through."""

from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.urls import reverse


class CandidateQuerySet(models.QuerySet):
    def search(self, query: str) -> "CandidateQuerySet":
        """Return candidates matching every word of ``query`` in their name or email.

        Each word may match the first name, last name or email, ignoring case,
        so "ann lee" finds Ann Lee and "@example" finds every example.com
        address. A blank query returns everyone.
        """
        candidates = self
        for word in query.split():
            candidates = candidates.filter(
                Q(first_name__icontains=word)
                | Q(last_name__icontains=word)
                | Q(email__icontains=word)
            )
        return candidates


class Candidate(models.Model):
    """A person the company is tracking, whether or not they have applied yet.

    Emails are stored lowercased. Together with ``unique=True`` and the
    ``candidate_email_lowercase`` check, that makes them unique regardless of
    capital letters, even for writes that skip ``save()``.
    """

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(
        unique=True,
        error_messages={"unique": "A candidate with this email already exists."},
    )
    phone = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CandidateQuerySet.as_manager()

    class Meta:
        ordering = ["last_name", "first_name", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(email=Lower("email")),
                name="candidate_email_lowercase",
            ),
        ]

    def __str__(self) -> str:
        return self.full_name

    def save(self, *args, **kwargs) -> None:
        self.email = self.email.lower()
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("candidates:detail", args=[self.pk])

    def clean(self) -> None:
        # Lowercase before the form's uniqueness check, so "Ann@X.com" is
        # reported as a clash with "ann@x.com" instead of failing in the database.
        self.email = self.email.lower()

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


DUPLICATE_SOURCE_NAME = "duplicate_source_name"


class SourceCategory(models.TextChoices):
    """The four kinds of source. Also reachable as ``Source.Category``."""

    COMPANY_WEBSITE = "company_website", "Company website"
    JOB_BOARD = "job_board", "Job board"
    REFERRAL = "referral", "Referral"
    OTHER = "other", "Other"


class SourceQuerySet(models.QuerySet):
    def active(self) -> "SourceQuerySet":
        """Return the sources new applications may pick. Retired sources are left out."""
        return self.filter(is_active=True)

    def retired(self) -> "SourceQuerySet":
        """Return the retired sources, which old applications keep but new ones can't pick."""
        return self.filter(is_active=False)


class Source(models.Model):
    """A recruiting channel an application came from, such as a job board or a referral.

    Sources are never deleted: they are retired (``is_active=False``) so old
    applications keep them while new ones can't pick them.
    """

    Category = SourceCategory

    name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=Category.choices)
    is_active = models.BooleanField(default=True)

    objects = SourceQuerySet.as_manager()

    class Meta:
        ordering = [Lower("name"), "pk"]
        constraints = [
            # Names keep the capitals they were typed with; only uniqueness ignores case.
            models.UniqueConstraint(
                Lower("name"),
                name="source_name_unique_ignoring_case",
                violation_error_message="A source with this name already exists.",
                violation_error_code=DUPLICATE_SOURCE_NAME,
            ),
            models.CheckConstraint(
                condition=models.Q(category__in=SourceCategory.values),
                name="source_category_valid",
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
                key = "name" if item.code == DUPLICATE_SOURCE_NAME else NON_FIELD_ERRORS
                errors.setdefault(key, []).append(item)
            raise ValidationError(errors) from None

    def retire(self) -> None:
        """Hide this source from new applications. Existing applications keep it."""
        if self.is_active:
            self.is_active = False
            self.save(update_fields=["is_active"])

    def reactivate(self) -> None:
        """Make a retired source available to new applications again."""
        if not self.is_active:
            self.is_active = True
            self.save(update_fields=["is_active"])
