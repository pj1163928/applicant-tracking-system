"""Template filters that expose ``accounts.roles`` so templates never duplicate the rules."""

from django import template

from accounts import permissions, roles

register = template.Library()


@register.filter
def role_label(user: roles.AnyUser) -> str:
    """Display the user's role: ``{{ user|role_label }}``."""
    return roles.role_label(user)


@register.filter
def can_make_changes(user: roles.AnyUser) -> bool:
    """Hide change actions from view-only users: ``{% if user|can_make_changes %}``."""
    return roles.can_make_changes(user)


@register.filter
def can_manage_candidates(user: roles.AnyUser) -> bool:
    """Show candidate add and edit actions: ``{% if user|can_manage_candidates %}``."""
    return permissions.can_manage_candidates(user)
