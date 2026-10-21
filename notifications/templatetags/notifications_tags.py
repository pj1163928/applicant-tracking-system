"""Template tags for notifications: the Needs attention count in the navigation."""

from django import template

from accounts.roles import AnyUser
from notifications import attention

register = template.Library()


@register.simple_tag
def attention_count(user: AnyUser) -> int:
    """How many decisions wait on ``user``: ``{% attention_count user as count %}``."""
    return attention.attention_count(user)
