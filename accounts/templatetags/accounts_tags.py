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
    """Show candidate add, edit and archive actions: ``{% if user|can_manage_candidates %}``."""
    return permissions.can_manage_candidates(user)


@register.filter
def can_delete_candidates(user: roles.AnyUser) -> bool:
    """Show the permanent-delete action: ``{% if user|can_delete_candidates %}``."""
    return permissions.can_delete_candidates(user)


@register.filter
def can_manage_sources(user: roles.AnyUser) -> bool:
    """Show source add, rename and retire actions: ``{% if user|can_manage_sources %}``."""
    return permissions.can_manage_sources(user)


@register.filter
def can_manage_openings(user: roles.AnyUser) -> bool:
    """Show opening create and edit actions: ``{% if user|can_manage_openings %}``."""
    return permissions.can_manage_openings(user)


@register.filter
def can_manage_applications(user: roles.AnyUser) -> bool:
    """Show record and edit-source actions: ``{% if user|can_manage_applications %}``."""
    return permissions.can_manage_applications(user)


@register.filter
def can_move_applications(user: roles.AnyUser) -> bool:
    """Show stage-move controls: ``{% if user|can_move_applications %}``."""
    return permissions.can_move_applications(user)


@register.filter
def can_make_offer(user: roles.AnyUser, opening) -> bool:
    """Whether Offer and Hired are open to the user: ``{% if user|can_make_offer:opening %}``."""
    return permissions.can_make_offer(user, opening)


@register.filter
def can_manage_opening_skills(user: roles.AnyUser, opening) -> bool:
    """Show skill add and remove controls: ``{% if user|can_manage_opening_skills:opening %}``."""
    return permissions.can_manage_opening_skills(user, opening)


@register.filter
def can_retire_skills(user: roles.AnyUser) -> bool:
    """Show skill retire and reactivate actions: ``{% if user|can_retire_skills %}``."""
    return permissions.can_retire_skills(user)


@register.filter
def can_decide_closure(user: roles.AnyUser, opening) -> bool:
    """Show closure decision actions: ``{% if user|can_decide_closure:opening %}``."""
    return permissions.can_decide_closure(user, opening)


@register.filter
def can_view_in_progress(user: roles.AnyUser) -> bool:
    """Show the in-progress view's link: ``{% if user|can_view_in_progress %}``."""
    return permissions.can_view_in_progress(user)
