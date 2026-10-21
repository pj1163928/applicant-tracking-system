"""The ``{% tailwind_stylesheet %}`` tag: the built Tailwind CSS, versioned by its build.

Django's development server serves static files with no caching instructions, so
a browser may go on using an old copy of the stylesheet after it is rebuilt
(VS Code's built-in browser keeps its copy even across sessions). Adding the
file's modification time to the URL gives every build a new address, so no
browser can serve a stale one.
"""

from pathlib import Path

from django import template
from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static
from django.utils.html import format_html
from django.utils.safestring import SafeString

register = template.Library()


@register.simple_tag
def tailwind_stylesheet() -> SafeString:
    """Render the ``<link>`` for the built Tailwind CSS, with ``?v=<modification time>``.

    Before the CSS has been built (in tests, for example) the link has no version.
    """
    path = settings.TAILWIND_CLI_DIST_CSS
    url = static(path)
    found = finders.find(path)
    if found:
        url = f"{url}?v={int(Path(found).stat().st_mtime)}"
    return format_html('<link rel="stylesheet" href="{}">', url)
