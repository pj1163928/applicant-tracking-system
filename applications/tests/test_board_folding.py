"""Busy columns fold to their newest three cards, expand with a search box, and empty
columns show an icon.

Expanding, searching and the empty box's height happen in the browser (the board's
script and assets/css/source.css), and are covered by docs/MANUAL_CHECKS.md. These
tests cover what the server renders for them.
"""

import re

import pytest

from applications.tests.test_board import HTMX, board_url, move_url, page, section
from candidates.models import Candidate

pytestmark = pytest.mark.django_db


@pytest.fixture
def applied(apply, backend, indeed):
    """Return a shortcut that records ``n`` applications for Backend Developer, oldest first."""

    def _applied(n):
        candidates = [
            Candidate.objects.create(first_name=f"Person{i}", last_name="Test", email=f"p{i}@x.com")
            for i in range(1, n + 1)
        ]
        return [apply(candidate, backend, indeed) for candidate in candidates]

    return _applied


def card_names(html: str, stage: str, end: str = "</section>") -> list[str]:
    column = section(html, f"column-{stage}", end)
    return re.findall(r'data-testid="card" data-name="([^"]+)"', column)


def folded_names(html: str, stage: str) -> list[str]:
    column = section(html, f"column-{stage}", "</section>")
    return re.findall(r'data-name="([^"]+)" data-beyond-fold', column)


def test_cards_are_newest_first(client, recruiter, applied, backend):
    applied(3)
    client.force_login(recruiter)

    html = page(client.get(board_url(backend)))

    assert card_names(html, "applied") == ["Person3 Test", "Person2 Test", "Person1 Test"]


def test_a_moved_card_goes_to_the_top_of_its_new_column(client, recruiter, applied, backend):
    first, second, third = applied(3)
    client.force_login(recruiter)
    for application in (third, second):
        client.post(move_url(application), {"to_stage": "screening", "expected_stage": "applied"})

    response = client.post(
        move_url(first), {"to_stage": "screening", "expected_stage": "applied"}, **HTMX
    )

    swapped = section(page(response), "swap-screening", "hx-swap-oob")  # the next swapped element
    names = re.findall(r'data-name="([^"]+)"', swapped)
    assert names == ["Person1 Test", "Person2 Test", "Person3 Test"]


def test_a_column_with_more_than_three_cards_folds_to_the_newest_three(
    client, recruiter, applied, backend
):
    applied(5)
    client.force_login(recruiter)

    html = page(client.get(board_url(backend)))

    assert card_names(html, "applied")[:3] == ["Person5 Test", "Person4 Test", "Person3 Test"]
    assert folded_names(html, "applied") == ["Person2 Test", "Person1 Test"]
    toggle = section(html, "fold-toggle", "</li>")
    assert "+2 more · Show all" in toggle
    assert "Show fewer" in toggle
    assert 'aria-expanded="false"' in toggle


@pytest.mark.parametrize("count", [0, 1, 3])
def test_a_column_with_three_or_fewer_cards_doesnt_fold(client, recruiter, applied, backend, count):
    applied(count)
    client.force_login(recruiter)

    html = page(client.get(board_url(backend)))

    assert folded_names(html, "applied") == []
    assert 'data-testid="fold-toggle"' not in html


def test_every_column_has_a_search_box_outside_its_swapped_cards(client, recruiter, app, backend):
    client.force_login(recruiter)

    html = page(client.get(board_url(backend)))

    for stage in ("applied", "screening", "hired", "rejected", "withdrawn"):
        box = html.index(f'data-testid="stage-search-{stage}"')
        # Before the cards list, which a move swaps, so what was typed survives a move.
        assert box < html.index(f'id="cards-{stage}"')
    assert 'aria-label="Search applicants at Screening"' in html
    assert 'data-name="Ann Lee"' in html  # what the search matches


def test_a_move_redraws_the_fold_toggle_with_the_new_count(client, recruiter, applied, backend):
    applications = applied(5)
    client.force_login(recruiter)

    response = client.post(
        move_url(applications[-1]),
        {"to_stage": "screening", "expected_stage": "applied"},
        **HTMX,
    )

    swapped = section(page(response), "swap-applied", "hx-swap-oob")  # the next swapped element
    assert "+1 more · Show all" in swapped


def test_a_move_out_of_a_folded_column_can_remove_its_toggle(client, recruiter, applied, backend):
    applications = applied(4)
    client.force_login(recruiter)

    response = client.post(
        move_url(applications[-1]),
        {"to_stage": "screening", "expected_stage": "applied"},
        **HTMX,
    )

    swapped = section(page(response), "swap-applied", "hx-swap-oob")  # the next swapped element
    assert 'data-testid="fold-toggle"' not in swapped
    assert "data-beyond-fold" not in swapped


def test_an_empty_column_shows_an_icon(client, recruiter, app, backend):
    client.force_login(recruiter)

    html = page(client.get(board_url(backend)))

    empty = section(html, "column-screening", "</section>")
    placeholder = empty[empty.index('data-testid="column-empty"') :]
    assert "<svg" in placeholder[: placeholder.index("</li>")]
    assert "No one at Screening." in placeholder
