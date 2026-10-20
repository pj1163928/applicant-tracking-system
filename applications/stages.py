"""The eight hiring stages an application moves through.

A pure module: Phase 6 adds the allowed-transitions table, ``can_move`` and
``requires_note`` here. Applications start at ``APPLIED``.
"""

from django.db import models


class Stage(models.TextChoices):
    """Every stage, in pipeline order. Hired, Rejected and Withdrawn are terminal."""

    APPLIED = "applied", "Applied"
    SCREENING = "screening", "Screening"
    INTERVIEW = "interview", "Interview"
    FINAL_REVIEW = "final_review", "Final Review"
    OFFER = "offer", "Offer"
    HIRED = "hired", "Hired"
    REJECTED = "rejected", "Rejected"
    WITHDRAWN = "withdrawn", "Withdrawn"
