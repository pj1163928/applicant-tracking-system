"""Template tags for the Admin in-progress view: its counts in the navigation."""

from django import template

from openings import in_progress

register = template.Library()


@register.simple_tag
def in_progress_counts() -> in_progress.InProgressCounts:
    """Today's in-progress counts by status: ``{% in_progress_counts as counts %}``."""
    return in_progress.in_progress_counts()
