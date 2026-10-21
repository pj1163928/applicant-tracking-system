"""The versioned Tailwind stylesheet link, so browsers never keep a stale copy."""

import os

import pytest
from django.template import Context, Template
from django.urls import reverse

from config.templatetags import stylesheets


def render() -> str:
    return Template("{% load stylesheets %}{% tailwind_stylesheet %}").render(Context())


def test_the_link_carries_the_built_files_modification_time(monkeypatch, tmp_path):
    built = tmp_path / "tailwind.css"
    built.write_text("/* built */")
    os.utime(built, (1_760_000_000, 1_760_000_000))
    monkeypatch.setattr(stylesheets.finders, "find", lambda path: str(built))

    html = render()

    assert html == '<link rel="stylesheet" href="/static/css/tailwind.css?v=1760000000">'


def test_a_rebuild_changes_the_address(monkeypatch, tmp_path):
    built = tmp_path / "tailwind.css"
    built.write_text("/* built */")
    monkeypatch.setattr(stylesheets.finders, "find", lambda path: str(built))
    os.utime(built, (1_760_000_000, 1_760_000_000))
    before = render()

    os.utime(built, (1_760_000_060, 1_760_000_060))

    assert render() != before


def test_before_the_css_is_built_the_link_has_no_version(monkeypatch):
    monkeypatch.setattr(stylesheets.finders, "find", lambda path: None)

    assert render() == '<link rel="stylesheet" href="/static/css/tailwind.css">'


@pytest.mark.django_db
def test_every_page_links_the_versioned_stylesheet(client, monkeypatch, tmp_path):
    built = tmp_path / "tailwind.css"
    built.write_text("/* built */")
    os.utime(built, (1_760_000_000, 1_760_000_000))
    monkeypatch.setattr(stylesheets.finders, "find", lambda path: str(built))

    html = client.get(reverse("accounts:login")).content.decode()

    assert 'href="/static/css/tailwind.css?v=1760000000"' in html
