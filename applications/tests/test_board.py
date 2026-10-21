"""The pipeline board, its Move menus, the move endpoint and the stage history pages."""

import re
from html import unescape

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from applications.models import Application, StageChange
from applications.services import move_application
from applications.stages import Stage
from candidates.models import Candidate

pytestmark = pytest.mark.django_db

HTMX = {"HTTP_HX_REQUEST": "true"}


def board_url(opening) -> str:
    return reverse("openings:board", args=[opening.pk])


def move_url(application) -> str:
    return reverse("applications:move", args=[application.pk])


def walk(application, *stages, by, note="Test setup.") -> None:
    """Move an application along ``stages`` through the service, to set up a test."""
    for stage in stages:
        move_application(application, stage, by=by, note=note)


def stored(application) -> tuple[str, int]:
    fresh = Application.objects.get(pk=application.pk)
    return fresh.stage, fresh.stage_changes.count()


def page(response) -> str:
    """The response body as text, with HTML entities such as &#x27; turned back into characters."""
    return unescape(response.content.decode())


def message_texts(response) -> list[str]:
    return [str(m) for m in get_messages(response.wsgi_request)]


def section(html: str, testid: str, end: str) -> str:
    """The HTML from the element with ``data-testid=testid`` to the next ``end``."""
    start = html.index(f'data-testid="{testid}"')
    return html[start : html.index(end, start)]


def menu_stages(html: str) -> list[str]:
    return re.findall(r'data-testid="move-(?!menu)([a-z_]+)"', html)


# The board page


def test_anonymous_users_are_sent_to_log_in(client, backend):
    response = client.get(board_url(backend))

    assert response.status_code == 302
    assert response.url.startswith(reverse("accounts:login"))


@pytest.mark.parametrize(
    "user_fixture", ["admin", "recruiter", "hiring_manager", "interviewer", "no_role_user"]
)
def test_every_role_sees_a_column_per_stage_with_each_card_in_its_stage(
    client, request, user_fixture, app, apply, ben, backend, linkedin, admin
):
    rejected = apply(ben, backend, linkedin)
    walk(rejected, Stage.REJECTED, by=admin)
    client.force_login(request.getfixturevalue(user_fixture))

    html = page(client.get(board_url(backend)))

    for stage in Stage:
        assert f'data-testid="column-{stage}"' in html
    assert "Ann Lee" in section(html, "column-applied", "</section>")
    assert "Ben Ortiz" in section(html, "column-rejected", "</details>")


def test_rejected_and_withdrawn_are_collapsed_to_a_count_that_expands(
    client, recruiter, app, apply, ben, backend, linkedin, admin
):
    rejected = apply(ben, backend, linkedin)
    walk(rejected, Stage.REJECTED, by=admin)
    client.force_login(recruiter)

    html = page(client.get(board_url(backend)))

    rejected_column = section(html, "column-rejected", "</details>")
    assert rejected_column.startswith('data-testid="column-rejected"')
    # Rejected and Withdrawn, closed: no `open` attribute on either <details>.
    assert len(re.findall(r"<details (?![^>]*\bopen\b)[^>]*data-testid=\"column-", html)) == 2
    assert re.search(r'data-testid="count-rejected">1<', html)
    assert re.search(r'data-testid="count-withdrawn">0<', html)
    # Expanding shows the cards: they're inside the <details>, not left out.
    assert "Ben Ortiz" in rejected_column
    assert "No one at Withdrawn." in section(html, "column-withdrawn", "</details>")


@pytest.mark.parametrize("user_fixture", ["interviewer", "no_role_user"])
def test_view_only_users_see_the_board_with_no_move_controls(
    client, request, user_fixture, app, backend
):
    client.force_login(request.getfixturevalue(user_fixture))

    response = client.get(board_url(backend))

    html = page(response)
    assert response.status_code == 200
    assert "Ann Lee" in html
    assert 'data-testid="view-only"' in html
    assert 'data-testid="move-menu"' not in html
    assert menu_stages(html) == []
    assert move_url(app) not in html
    assert 'data-testid="history-link"' in html  # history is still visible


def test_the_move_menu_lists_only_legal_targets_tagged_by_what_they_ask_for(
    client, hiring_manager, app, backend
):
    client.force_login(hiring_manager)

    html = page(client.get(board_url(backend)))

    menu = section(html, "move-menu", "</details>")
    assert menu_stages(menu) == [
        "screening",
        "interview",
        "final_review",
        "offer",
        "rejected",
        "withdrawn",
    ]
    assert re.search(r'Screening\s*<span class="badge[^"]*" data-testid="tag-next"', menu)
    assert re.search(r'Interview\s*<span class="badge[^"]*" data-testid="tag-note"', menu)
    assert re.search(r'Rejected\s*<span class="badge[^"]*" data-testid="tag-optional-note"', menu)
    assert 'data-testid="offer-withheld-hint"' not in menu


def test_without_offer_authority_the_menu_leaves_out_offer_and_says_who_can(
    client, recruiter, app, backend
):
    client.force_login(recruiter)

    html = page(client.get(board_url(backend)))

    menu = section(html, "move-menu", "</details>")
    assert "offer" not in menu_stages(menu)
    assert "Offer is only for Admins, Hiring Managers or Hal Manager." in menu
    assert 'data-testid="offer-withheld"' in html


def test_the_designated_authority_gets_offer_in_the_menu(
    client, make_opening, make_user, apply, ann, indeed
):
    riley = make_user("riley", "Recruiter", first_name="Riley", last_name="Chen")
    support = make_opening("Support Specialist", riley)
    apply(ann, support, indeed)
    client.force_login(riley)

    html = page(client.get(board_url(support)))

    assert "offer" in menu_stages(html)
    assert 'data-testid="offer-allowed"' in html


def test_a_hired_card_has_no_move_menu(client, admin, app, backend):
    walk(
        app,
        Stage.SCREENING,
        Stage.INTERVIEW,
        Stage.FINAL_REVIEW,
        Stage.OFFER,
        Stage.HIRED,
        by=admin,
    )
    client.force_login(admin)

    html = page(client.get(board_url(backend)))

    assert "Ann Lee" in section(html, "column-hired", "</section>")
    assert 'data-testid="move-menu"' not in html


def archive(candidate) -> None:
    """Archive directly, as the archive service would once nothing is active."""
    Candidate.objects.filter(pk=candidate.pk).update(is_archived=True, archived_at=timezone.now())


def test_an_archived_candidates_card_stays_on_the_board_without_move_controls(
    client, recruiter, interviewer, app, backend
):
    walk(app, Stage.WITHDRAWN, by=recruiter)
    archive(app.candidate)

    for user in (recruiter, interviewer):
        client.force_login(user)
        html = page(client.get(board_url(backend)))
        start = html.index(f'id="card-{app.pk}"')
        card = html[start : html.index("</li>", start)]
        assert "Ann Lee" in section(html, "column-withdrawn", "</details>")
        assert 'data-testid="archived-badge"' in card
        assert 'data-testid="move-menu"' not in card
        assert "data-move-targets" not in card
        assert "data-drop-form" not in card
        # Only someone who could otherwise move it is told how to.
        assert ('data-testid="archived-no-moves"' in card) == (user == recruiter)


def test_a_reopen_posted_for_an_archived_candidate_is_refused_with_400(client, recruiter, app):
    walk(app, Stage.REJECTED, by=recruiter)
    archive(app.candidate)
    client.force_login(recruiter)

    response = client.post(
        move_url(app),
        {"to_stage": "screening", "expected_stage": "rejected", "confirmed": "on", "note": "Hm."},
        **HTMX,
    )

    assert response.status_code == 400
    assert "Ann Lee is archived, so their applications can't be moved. Unarchive them first." in (
        page(response)
    )
    assert stored(app) == (Stage.REJECTED, 2)


def test_each_menu_entry_carries_the_stage_its_card_shows(client, recruiter, app, backend):
    client.force_login(recruiter)

    html = page(client.get(board_url(backend)))

    menu = section(html, "move-menu", "</details>")
    assert menu.count('name="expected_stage" value="applied"') == len(menu_stages(menu))


def test_the_opening_page_links_to_its_board_for_every_role(client, interviewer, app, backend):
    client.force_login(interviewer)

    html = page(client.get(backend.get_absolute_url()))

    assert f'href="{board_url(backend)}"' in html
    assert reverse("applications:history", args=[app.pk]) in html


# The move endpoint: moves that go through


def test_a_one_step_move_swaps_only_the_two_affected_columns(client, recruiter, app):
    client.force_login(recruiter)

    response = client.post(
        move_url(app), {"to_stage": "screening", "expected_stage": "applied"}, **HTMX
    )

    html = page(response)
    assert response.status_code == 200
    assert "<html" not in html
    assert "Moved Ann Lee from Applied to Screening." in html
    assert re.findall(r'data-testid="swap-([a-z_]+)"', html) == ["applied", "screening"]
    assert "Ann Lee" in section(html, "swap-screening", "</ul>")
    assert "No one at Applied." in section(html, "swap-applied", "</ul>")
    assert 'id="dialog-slot" hx-swap-oob="innerHTML"' in html  # closes any note dialog
    assert "HX-Request" in response["Vary"]
    assert stored(app) == (Stage.SCREENING, 2)


def test_without_htmx_a_move_redirects_back_to_the_board(client, recruiter, app, backend):
    client.force_login(recruiter)

    response = client.post(move_url(app), {"to_stage": "screening", "expected_stage": "applied"})

    assert response.status_code == 302
    assert response.url == board_url(backend)
    assert message_texts(response) == ["Moved Ann Lee from Applied to Screening."]
    assert stored(app) == (Stage.SCREENING, 2)


def test_the_moved_card_offers_the_moves_from_its_new_stage(client, recruiter, app):
    client.force_login(recruiter)

    html = page(
        client.post(move_url(app), {"to_stage": "screening", "expected_stage": "applied"}, **HTMX)
    )

    card = section(html, "swap-screening", "</ul>")
    assert 'name="expected_stage" value="screening"' in card
    assert menu_stages(card)[0] == "applied"


# The move endpoint: the note prompt versus a required note


def test_a_skip_prompts_for_a_required_note_before_anything_is_written(client, recruiter, app):
    client.force_login(recruiter)

    response = client.post(
        move_url(app), {"to_stage": "interview", "expected_stage": "applied"}, **HTMX
    )

    html = page(response)
    assert response.status_code == 200
    assert response["HX-Retarget"] == "#dialog-slot"
    assert 'data-testid="note-dialog"' in html
    assert "This skips Screening. Say why it's being expedited." in html
    assert re.search(r"<textarea[^>]*\brequired\b", html)
    assert "(optional)" not in html
    assert 'name="confirmed" value="on"' in html
    assert stored(app) == (Stage.APPLIED, 1)


def test_a_required_note_left_blank_is_refused_and_the_dialog_shown_again(client, recruiter, app):
    client.force_login(recruiter)

    response = client.post(
        move_url(app),
        {"to_stage": "interview", "expected_stage": "applied", "confirmed": "on", "note": "  "},
        **HTMX,
    )

    html = page(response)
    assert response["HX-Retarget"] == "#dialog-slot"
    assert "Add a note to say why Ann Lee is skipping ahead to Interview." in html
    assert 'data-testid="error-note"' in html
    assert stored(app) == (Stage.APPLIED, 1)


def test_a_confirmed_move_with_its_note_is_made(client, recruiter, app):
    client.force_login(recruiter)

    response = client.post(
        move_url(app),
        {
            "to_stage": "interview",
            "expected_stage": "applied",
            "confirmed": "on",
            "note": "Already screened by phone.",
        },
        **HTMX,
    )

    assert response.status_code == 200
    assert stored(app) == (Stage.INTERVIEW, 2)
    assert app.stage_changes.last().note == "Already screened by phone."


@pytest.mark.parametrize("to_stage", ["rejected", "withdrawn"])
def test_rejecting_or_withdrawing_prompts_for_an_optional_note(client, recruiter, app, to_stage):
    client.force_login(recruiter)

    response = client.post(
        move_url(app), {"to_stage": to_stage, "expected_stage": "applied"}, **HTMX
    )

    html = page(response)
    assert response["HX-Retarget"] == "#dialog-slot"
    assert "(optional)" in html
    assert not re.search(r"<textarea[^>]*\brequired\b", html)
    assert stored(app) == (Stage.APPLIED, 1)


def test_a_confirmed_rejection_needs_no_note(client, recruiter, app):
    client.force_login(recruiter)

    response = client.post(
        move_url(app),
        {"to_stage": "rejected", "expected_stage": "applied", "confirmed": "on", "note": ""},
        **HTMX,
    )

    assert "Moved Ann Lee from Applied to Rejected." in page(response)
    assert stored(app) == (Stage.REJECTED, 2)
    assert app.stage_changes.last().note == ""


def test_a_one_step_move_never_prompts(client, recruiter, app):
    client.force_login(recruiter)

    response = client.post(
        move_url(app), {"to_stage": "screening", "expected_stage": "applied"}, **HTMX
    )

    assert "HX-Retarget" not in response
    assert 'data-testid="note-dialog"' not in page(response)


def test_without_htmx_the_note_prompt_is_a_page(client, recruiter, app):
    client.force_login(recruiter)

    response = client.post(move_url(app), {"to_stage": "interview", "expected_stage": "applied"})

    html = page(response)
    assert response.status_code == 200
    assert "<html" in html
    assert 'data-testid="note-form"' in html
    assert "hx-post" not in section(html, "note-form", ">")
    assert stored(app) == (Stage.APPLIED, 1)


# The move endpoint: refusals posted straight to it


@pytest.mark.parametrize("user_fixture", ["interviewer", "no_role_user"])
def test_view_only_users_are_refused_with_403_and_nothing_is_written(
    client, request, user_fixture, app
):
    client.force_login(request.getfixturevalue(user_fixture))

    response = client.post(
        move_url(app), {"to_stage": "screening", "expected_stage": "applied"}, **HTMX
    )

    assert response.status_code == 403
    assert stored(app) == (Stage.APPLIED, 1)


def test_the_endpoint_takes_posts_only(client, recruiter, app):
    client.force_login(recruiter)

    assert client.get(move_url(app)).status_code == 405


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (
            {"to_stage": "hired", "expected_stage": "applied"},
            "Ann Lee can only be moved to Hired from Offer.",
        ),
        ({"to_stage": "applied", "expected_stage": "applied"}, "Ann Lee is already at Applied."),
        ({"to_stage": "promoted", "expected_stage": "applied"}, "That isn't a hiring stage."),
        ({"to_stage": "screening"}, "This move didn't say which stage its card showed."),
        # Saying "confirmed" never gets an illegal move past the rules.
        (
            {
                "to_stage": "hired",
                "expected_stage": "applied",
                "confirmed": "on",
                "note": "Please.",
            },
            "Ann Lee can only be moved to Hired from Offer.",
        ),
    ],
)
def test_an_illegal_move_is_refused_with_400_and_a_clear_message(client, admin, app, data, message):
    client.force_login(admin)

    response = client.post(move_url(app), data, **HTMX)

    html = page(response)
    assert response.status_code == 400
    assert message in html
    assert 'data-testid="board-message"' in html
    assert "swap-applied" in html  # the card's column is redrawn as it really is
    assert stored(app) == (Stage.APPLIED, 1)


@pytest.mark.parametrize(("start", "to_stage"), [("final_review", "offer"), ("offer", "hired")])
def test_a_move_into_offer_or_hired_without_authority_is_refused_with_403(
    client, recruiter, admin, app, start, to_stage
):
    path = [Stage.SCREENING, Stage.INTERVIEW, Stage.FINAL_REVIEW, Stage.OFFER]
    walk(app, *path[: path.index(start) + 1], by=admin)
    before = stored(app)
    client.force_login(recruiter)

    response = client.post(
        move_url(app), {"to_stage": to_stage, "expected_stage": start, "confirmed": "on"}, **HTMX
    )

    assert response.status_code == 403
    assert (
        "Only Admins, Hiring Managers or Hal Manager, this opening's designated authority, "
        f"can move applicants into {Stage(to_stage).label}." in page(response)
    )
    assert stored(app) == before


def test_a_stale_card_is_refused_and_both_columns_are_redrawn(client, recruiter, admin, app):
    walk(app, Stage.SCREENING, by=admin)  # someone else moved Ann after the board loaded
    client.force_login(recruiter)

    response = client.post(
        move_url(app), {"to_stage": "rejected", "expected_stage": "applied"}, **HTMX
    )

    html = page(response)
    assert response.status_code == 400
    assert "Ann Lee has moved to Screening since this board loaded" in html
    assert re.findall(r'data-testid="swap-([a-z_]+)"', html) == ["applied", "screening"]
    assert "Ann Lee" in section(html, "swap-screening", "</ul>")
    assert stored(app) == (Stage.SCREENING, 2)


def test_a_repeated_submission_moves_once(client, recruiter, app):
    client.force_login(recruiter)
    data = {"to_stage": "screening", "expected_stage": "applied"}

    first = client.post(move_url(app), data, **HTMX)
    second = client.post(move_url(app), data, **HTMX)

    assert (first.status_code, second.status_code) == (200, 400)
    assert stored(app) == (Stage.SCREENING, 2)


def test_without_htmx_a_refusal_shows_the_board_with_the_message(client, admin, app):
    client.force_login(admin)

    response = client.post(move_url(app), {"to_stage": "hired", "expected_stage": "applied"})

    assert response.status_code == 400
    assert "<html" in page(response)
    assert message_texts(response) == ["Ann Lee can only be moved to Hired from Offer."]
    assert stored(app) == (Stage.APPLIED, 1)


def test_moves_on_a_closed_opening_still_work(client, recruiter, app, backend):
    backend.status = backend.Status.CLOSED
    backend.save()
    client.force_login(recruiter)

    response = client.post(
        move_url(app), {"to_stage": "screening", "expected_stage": "applied"}, **HTMX
    )

    assert response.status_code == 200
    assert stored(app) == (Stage.SCREENING, 2)


# Stage history


def test_htmx_gets_the_history_as_a_dialog_newest_first(client, interviewer, admin, app):
    walk(app, Stage.INTERVIEW, by=admin, note="Already screened by phone.")
    client.force_login(interviewer)

    response = client.get(reverse("applications:history", args=[app.pk]), **HTMX)

    html = page(response)
    assert response.status_code == 200
    assert "<html" not in html
    assert 'data-testid="history-dialog"' in html
    assert html.count('data-testid="history-row"') == 2
    assert html.index("Applied → Interview") < html.index("Recorded at Applied")
    assert "Already screened by phone." in html
    assert "Ada Admin" in html and "Rae Recruiter" in html
    assert "HX-Request" in response["Vary"]


def test_without_htmx_the_history_is_a_page(client, interviewer, app):
    client.force_login(interviewer)

    response = client.get(reverse("applications:history", args=[app.pk]))

    html = page(response)
    assert "<html" in html
    assert "Recorded at Applied" in html
    assert StageChange.objects.filter(application=app).count() == 1
