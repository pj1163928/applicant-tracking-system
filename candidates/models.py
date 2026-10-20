"""Candidates: the people staff track. Candidates never log in."""

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
