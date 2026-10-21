"""Drag-and-drop on the pipeline board, and the board's layout.

The drag itself happens in the browser and is covered by the manual checklist
in docs/MANUAL_CHECKS.md. These tests cover what the server sends for it: which
cards can be dragged and the hints they carry, and that the drop form each card
renders, posted as a drop would post it, gets the same answers as the Move menu.
"""

import re

import pytest

from applications.models import StageChange
from applications.services import move_application
from applications.stages import Stage
from applications.tests.test_board import (
    HTMX,
    board_url,
    menu_stages,
    move_url,
    page,
    section,
    stored,
    walk,
)

pytestmark = pytest.mark.django_db

PIPELINE_ORDER = ["applied", "screening", "interview", "final_review", "offer", "hired"]


def card_tag(html: str, application) -> str:
    """The card's opening <li> tag, with its drag attributes."""
    return re.search(rf'<li [^>]*id="card-{application.pk}"[^>]*>', html).group(0)


def card_attr(html: str, application, name: str) -> str | None:
    match = re.search(rf'{name}="([^"]*)"', card_tag(html, application))
    return match.group(1) if match else None


def card_html(html: str, application) -> str:
    """The card's markup, from its <li> up to its drop form."""
    start = html.index(f'id="card-{application.pk}"')
    return html[start : html.index('data-testid="drop-form"', start)]


def drop_form(html: str, application) -> tuple[str, dict[str, str]]:
    """The card's hidden drop form: where it posts, and the fields it sends."""
    for action, body in re.findall(
        r'<form method="post" action="([^"]+)"[^>]*data-testid="drop-form">(.*?)</form>',
        html,
        re.DOTALL,
    ):
        if action == move_url(application):
            fields = re.findall(r'<input type="hidden" name="(\w+)" value="([^"]*)"', body)
            return action, dict(fields)
    raise AssertionError(f"No drop form for application {application.pk}")


def drop(client, html: str, application, stage: str):
    """Post the card's drop form, as the board's script does when it lands on ``stage``."""
    action, fields = drop_form(html, application)
    fields.pop("csrfmiddlewaretoken", None)
    return client.post(action, fields | {"to_stage": stage}, **HTMX)


def submit_dialog(client, body: str, note: str = ""):
    """Submit the dialog a drop opened, as clicking its Move button does."""
    action, form = re.search(
        r'<form method="post" action="([^"]+)".*?data-testid="note-form">(.*?)</form>',
        body,
        re.DOTALL,
    ).groups()
    fields = dict(re.findall(r'<input type="hidden" name="(\w+)" value="([^"]*)"', form))
    fields.pop("csrfmiddlewaretoken", None)
    if "<textarea" in form:
        fields["note"] = note
    return client.post(action, fields, **HTMX)


# The layout: the whole board fits the page, with no sideways scrolling


def test_the_pipeline_is_a_grid_in_stage_order_with_an_arrow_between_stages(
    client, recruiter, app, backend
):
    client.force_login(recruiter)

    html = page(client.get(board_url(backend)))

    assert "overflow-x-auto" not in html
    pipeline = section(html, "board", 'data-testid="closed-stages"')
    found = re.findall(r'data-testid="(column-(?!empty)[a-z_]+|stage-arrow)"', pipeline)
    expected = []
    for stage in PIPELINE_ORDER:
        expected += [f"column-{stage}", "stage-arrow"]
    assert found == expected[:-1]  # an arrow between each pair, none after Hired
    # From md up, the arrow after Interview wraps to the second row of three.
    arrows = pipeline.split('data-testid="stage-arrow"')
    assert ["md:col-span-full" in arrow for arrow in arrows[:-1]] == [
        False,
        False,
        True,
        False,
        False,
    ]


def test_rejected_and_withdrawn_sit_apart_from_the_pipeline(
    client, recruiter, app, apply, ben, backend, linkedin, admin
):
    walk(apply(ben, backend, linkedin), Stage.REJECTED, by=admin)
    client.force_login(recruiter)

    html = page(client.get(board_url(backend)))

    pipeline = section(html, "board", 'data-testid="closed-stages"')
    closed = section(html, "closed-stages", 'id="dialog-slot"')
    for stage in ("rejected", "withdrawn"):
        assert f'data-testid="column-{stage}"' not in pipeline
        assert f'data-testid="column-{stage}"' in closed
    # Both sit inside the area where cards can be dropped.
    drop_area = html[html.index("<div data-drop-area>") : html.index('id="dialog-slot"')]
    assert 'data-testid="column-applied"' in drop_area
    assert 'data-testid="column-withdrawn"' in drop_area
    assert "Ben Ortiz" in section(html, "column-rejected", "</details>")


# Which cards can be dragged


def test_a_movers_card_is_draggable_and_hints_at_its_move_menu_targets(
    client, hiring_manager, app, backend
):
    client.force_login(hiring_manager)

    html = page(client.get(board_url(backend)))

    # Dragged by the board's pointer-event script (mouse and touch), not the browser's own
    # drag-and-drop, so there's no draggable attribute; the grip shows it can be picked up.
    assert card_attr(html, app, "draggable") is None
    assert 'title="Drag to another stage"' in card_html(html, app)
    targets = card_attr(html, app, "data-move-targets").split()
    assert targets == menu_stages(card_html(html, app))  # the same moves as its Move menu
    assert targets == ["screening", "interview", "final_review", "offer", "rejected", "withdrawn"]
    # Skips need a note, and Rejected and Withdrawn ask for an optional one.
    assert card_attr(html, app, "data-note-targets").split() == [
        "interview",
        "final_review",
        "offer",
        "rejected",
        "withdrawn",
    ]
    assert 'data-testid="drag-legend"' in html
    assert "Drag a card to another stage (on a touch screen, press and hold it first)" in html
    assert 'data-testid="drop-hint"' not in html  # no text hints inside the columns


def test_a_card_without_offer_authority_does_not_hint_at_offer(client, recruiter, app, backend):
    client.force_login(recruiter)

    html = page(client.get(board_url(backend)))

    assert "offer" not in card_attr(html, app, "data-move-targets").split()


def test_a_drop_form_carries_the_stage_its_card_shows(client, recruiter, app, backend):
    client.force_login(recruiter)

    html = page(client.get(board_url(backend)))

    action, fields = drop_form(html, app)
    assert action == move_url(app)
    assert fields["expected_stage"] == "applied"
    assert fields["to_stage"] == ""  # the board's script fills it in on a drop
    assert fields["dropped"] == "on"  # so even a routine move is confirmed first
    assert "csrfmiddlewaretoken" in fields


@pytest.mark.parametrize("user_fixture", ["interviewer", "no_role_user"])
def test_view_only_users_cant_drag(client, request, user_fixture, app, backend):
    client.force_login(request.getfixturevalue(user_fixture))

    html = page(client.get(board_url(backend)))

    assert "Ann Lee" in html
    assert "data-move-targets=" not in html  # the board's script only picks these up
    assert 'title="Drag to another stage"' not in html
    assert 'data-testid="drop-form"' not in html
    assert 'data-testid="drag-legend"' not in html


def test_a_hired_card_cant_be_dragged(client, admin, app, backend):
    walk(app, Stage.SCREENING, Stage.INTERVIEW, Stage.FINAL_REVIEW, Stage.OFFER, by=admin)
    walk(app, Stage.HIRED, by=admin)
    client.force_login(admin)

    html = page(client.get(board_url(backend)))

    assert card_attr(html, app, "data-move-targets") is None
    assert 'data-testid="drop-form"' not in html


# Dropping a card


def test_a_drop_on_a_legal_column_asks_for_confirmation_before_moving(
    client, recruiter, app, backend
):
    client.force_login(recruiter)
    html = page(client.get(board_url(backend)))

    response = drop(client, html, app, "screening")

    body = page(response)
    assert response.status_code == 200
    assert response["HX-Retarget"] == "#dialog-slot"
    assert 'data-testid="note-dialog"' in body
    assert (
        "You dropped Ann Lee on Screening. This moves them one step forward, "
        "from Applied to Screening." in body
    )
    assert "<textarea" not in body  # a routine move needs no note
    assert re.search(r'data-testid="note-submit" autofocus>\s*Move to Screening<', body)
    assert "Cancel" in body
    assert stored(app) == ("applied", 1)  # nothing written until it's confirmed


def test_a_confirmed_drop_moves_the_card_through_the_move_endpoint(client, recruiter, app, backend):
    client.force_login(recruiter)
    html = page(client.get(board_url(backend)))
    dialog = page(drop(client, html, app, "screening"))

    response = submit_dialog(client, dialog)

    body = page(response)
    assert response.status_code == 200
    assert "<html" not in body
    assert "Moved Ann Lee from Applied to Screening." in body
    assert stored(app) == ("screening", 2)
    assert re.findall(r'data-testid="swap-([a-z_]+)"', body) == ["applied", "screening"]
    # The card lands in its new column, animated, and draggable onward from there.
    landed = section(body, "swap-screening", "</ul>")
    assert 'data-move-targets="applied interview' in landed
    assert "animate-land motion-reduce:animate-none" in landed
    assert 'id="dialog-slot" hx-swap-oob="innerHTML"></div>' in body  # the dialog closes


def test_a_confirmed_drop_cant_be_submitted_twice(client, recruiter, app, backend):
    client.force_login(recruiter)
    html = page(client.get(board_url(backend)))
    dialog = page(drop(client, html, app, "screening"))
    submit_dialog(client, dialog)

    again = submit_dialog(client, dialog)

    assert again.status_code == 400
    assert stored(app) == ("screening", 2)


def test_the_move_menu_still_moves_a_routine_step_without_asking(client, recruiter, app):
    client.force_login(recruiter)

    response = client.post(
        move_url(app), {"to_stage": "screening", "expected_stage": "applied"}, **HTMX
    )

    assert response.status_code == 200
    assert "HX-Retarget" not in response
    assert stored(app) == ("screening", 2)


def test_without_htmx_a_drop_confirmation_is_a_page(client, recruiter, app):
    client.force_login(recruiter)

    response = client.post(
        move_url(app), {"to_stage": "screening", "expected_stage": "applied", "dropped": "on"}
    )

    body = page(response)
    assert response.status_code == 200
    assert "<html" in body
    assert "You dropped Ann Lee on Screening." in body
    assert stored(app) == ("applied", 1)


def test_a_drop_on_a_column_that_needs_a_note_opens_the_note_dialog_first(
    client, recruiter, app, backend
):
    client.force_login(recruiter)
    html = page(client.get(board_url(backend)))

    response = drop(client, html, app, "interview")

    body = page(response)
    assert response.status_code == 200
    assert response["HX-Retarget"] == "#dialog-slot"
    assert 'data-testid="note-dialog"' in body
    assert "This skips Screening. Say why it's being expedited." in body
    assert "<textarea" in body
    assert stored(app) == ("applied", 1)  # nothing written yet

    confirmed = submit_dialog(client, body, note="Strong referral; skipping the phone screen.")

    assert confirmed.status_code == 200
    assert stored(app) == ("interview", 2)
    assert StageChange.objects.filter(application=app).latest("pk").note.startswith("Strong")


@pytest.mark.parametrize(
    ("user_fixture", "path", "to_stage", "status", "message"),
    [
        # Hired is reachable only from Offer.
        ("admin", [], "hired", 400, "Hired"),
        # Rejected can only be reopened to an active stage.
        ("admin", [Stage.REJECTED], "withdrawn", 400, "Withdrawn"),
        # Only Admins, Hiring Managers or the designated authority can make offers.
        ("recruiter", [Stage.FINAL_REVIEW], "offer", 403, "Offer"),
    ],
)
def test_a_drop_on_an_illegal_column_is_refused_and_the_card_stays_where_it_was(
    client, request, admin, app, backend, user_fixture, path, to_stage, status, message
):
    walk(app, *path, by=admin)
    start = stored(app)
    client.force_login(request.getfixturevalue(user_fixture))
    html = page(client.get(board_url(backend)))

    response = drop(client, html, app, to_stage)

    body = page(response)
    assert response.status_code == status
    assert 'data-testid="board-message"' in body
    assert message in section(body, "board-message", "</div>")
    assert stored(app) == start
    assert 'data-testid="note-dialog"' not in body  # refused at once, no dialog first
    # The card's own column is redrawn with the card still in it, shaking where it stayed.
    column = section(body, f"swap-{start[0]}", "</ul>")
    assert re.search(rf'animate-shake[^"]*" id="card-{app.pk}"', column)


def test_a_drop_from_a_stale_card_is_refused(client, recruiter, admin, app, backend):
    client.force_login(recruiter)
    html = page(client.get(board_url(backend)))
    move_application(app, Stage.SCREENING, by=admin, note="")  # someone else moves it first

    response = drop(client, html, app, "screening")

    assert response.status_code == 400
    assert stored(app) == ("screening", 2)  # the history wasn't written twice


def test_view_only_users_posting_a_drop_are_refused(client, interviewer, recruiter, app, backend):
    client.force_login(recruiter)
    html = page(client.get(board_url(backend)))
    client.force_login(interviewer)

    response = drop(client, html, app, "screening")

    assert response.status_code == 403
    assert stored(app) == ("applied", 1)
