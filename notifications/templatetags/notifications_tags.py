"""Template tags for notifications: the Needs attention counts in the navigation."""

from django import template

from accounts.roles import AnyUser
from notifications import attention

register = template.Library()


@register.simple_tag
def attention_summary(user: AnyUser) -> attention.AttentionSummary:
    """The badge's count and its breakdown: ``{% attention_summary user as summary %}``."""
    return attention.attention_summary(user)
