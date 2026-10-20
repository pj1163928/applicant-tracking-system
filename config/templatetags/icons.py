"""The ``{% icon %}`` tag: inline Lucide SVG icons stored in ``templates/icons/``.

Registered as a template builtin (see ``TEMPLATES`` in settings), so every
template can use ``{% icon "house" "size-5" %}`` without ``{% load %}``.
To add an icon, copy its SVG from lucide-static (same pinned version, see
README) into ``templates/icons/<name>.svg``.
"""

import re
from functools import cache
from pathlib import Path

from django import template
from django.conf import settings
from django.utils.html import escape
from django.utils.safestring import SafeString, mark_safe

register = template.Library()

ICON_DIR = Path(settings.BASE_DIR) / "templates" / "icons"
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_ICON_NAME = re.compile(r"^[a-z0-9-]+$")


@cache
def _svg_source(name: str) -> str:
    """Return the icon's SVG with its license comment removed and whitespace collapsed."""
    path = ICON_DIR / f"{name}.svg"
    if not _ICON_NAME.match(name) or not path.is_file():
        raise template.TemplateSyntaxError(f"Unknown icon {name!r}: no templates/icons/{name}.svg")
    return " ".join(_COMMENT.sub("", path.read_text(encoding="utf-8")).split())


@register.simple_tag
def icon(name: str, css_class: str = "size-5") -> SafeString:
    """Render a decorative icon. Screen readers skip it, so pair it with visible text
    or an ``aria-label`` on the surrounding control."""
    attrs = f'class="{escape(css_class)} shrink-0" aria-hidden="true" focusable="false"'
    svg = _svg_source(name).replace(f'class="lucide lucide-{name}"', attrs, 1)
    return mark_safe(svg)
