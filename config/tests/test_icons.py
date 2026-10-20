import pytest
from django.template import Context, Template, TemplateSyntaxError


def render(source: str) -> str:
    return Template(source).render(Context())


def test_icon_renders_inline_svg_with_classes():
    html = render('{% icon "house" "size-4 opacity-60" %}')

    assert html.startswith("<svg ")
    assert 'class="size-4 opacity-60 shrink-0"' in html
    assert 'aria-hidden="true"' in html
    assert "license" not in html


def test_icon_defaults_to_size_5():
    assert 'class="size-5 shrink-0"' in render('{% icon "menu" %}')


@pytest.mark.parametrize("name", ["no-such-icon", "../base"])
def test_unknown_icon_is_an_error(name):
    with pytest.raises(TemplateSyntaxError):
        render(f'{{% icon "{name}" %}}')
