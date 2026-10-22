"""Template filters for showing stages: ``{% load stage_tags %}``."""

from django import template

from applications.stages import Stage

register = template.Library()

# The icon (templates/icons/<name>.svg) shown beside each stage's name, on the pipeline board
# and the home page's pipeline snapshot.
STAGE_ICONS: dict[Stage, str] = {
    Stage.APPLIED: "file-text",
    Stage.SCREENING: "scan-search",
    Stage.INTERVIEW: "messages-square",
    Stage.FINAL_REVIEW: "clipboard-check",
    Stage.OFFER: "mail-check",
    Stage.HIRED: "party-popper",
    Stage.REJECTED: "circle-x",
    Stage.WITHDRAWN: "undo-2",
}


@register.filter
def stage_icon(stage: str) -> str:
    """The icon name for ``stage``: ``{% icon column.stage|stage_icon "size-4" %}``."""
    return STAGE_ICONS[Stage(stage)]
