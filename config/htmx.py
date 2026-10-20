"""HTMX helpers shared by every app's views."""

from django.http import HttpRequest


def is_htmx_partial(request: HttpRequest) -> bool:
    """True for an HTMX request that wants a fragment, not a history restore of the full page."""
    return (
        request.headers.get("HX-Request") == "true"
        and request.headers.get("HX-History-Restore-Request") != "true"
    )
