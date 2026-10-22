"""The home page: what is the signed-in user's, and the numbers everyone shares."""

from html import unescape

import pytest
from django.urls import reverse

from accounts.dashboard import (
    FOLD_AT,
    Fold,
    applicants_on_your_openings,
    home_stats,
    pipeline_snapshot,
    recent_work,
    your_attention,
    your_openings,
)
from applications.models import Application
from applications.services import move_application, record_application
from applications.stages import Stage
from candidates.models import Candidate, Source
from openings.models import JobOpening

pytestmark = pytest.mark.django_db


def page(response) -> str:
    return unescape(response.content.decode())


@pytest.fixture
def source(db) -> Source:
    return Source.objects.create(name="Indeed", category=Source.Category.JOB_BOARD)


@pytest.fixture
def apply(source, admin):
    """Record an application through the service, for a new candidate called ``first``."""

    def _apply(first: str, opening: JobOpening, by=None) -> Application:
        candidate = Candidate.objects.create(
            first_name=first, last_name="Test", email=f"{first.lower()}@example.com"
        )
        return record_application(
            candidate=candidate, opening=opening, source=source, by=by or admin
        )

    return _apply


@pytest.fixture
def world(make_opening, hiring_manager, recruiter, apply):
    """The manager owns an open and a closed opening; the recruiter owns one open opening."""
    backend = make_opening("Backend Developer", hiring_manager)
    qa = make_opening("QA Analyst", hiring_manager)
    data = make_opening("Data Engineer", recruiter)
    ann = apply("Ann", backend, by=recruiter)
    ben = apply("Ben", backend)
    cy = apply("Cy", qa)
    dee = apply("Dee", data)
    move_application(ann, Stage.SCREENING, by=recruiter)
    move_application(ben, Stage.REJECTED, by=recruiter)
    JobOpening.objects.filter(pk=qa.pk).update(status=JobOpening.Status.CLOSED)
    return {
        "backend": backend,
        "qa": qa,
        "data": data,
        "ann": ann,
        "ben": ben,
        "cy": cy,
        "dee": dee,
    }


def test_home_stats_count_everyones_and_the_users_own(world, hiring_manager):
    stats = home_stats(hiring_manager)

    assert stats.open_openings == 2  # Backend Developer and Data Engineer
    assert stats.in_progress == 3  # Ann, Cy and Dee; Ben was rejected
    assert stats.your_openings == 2
    assert stats.your_in_progress == 2  # Ann and Cy


def test_your_openings_lists_the_users_openings_open_first_with_their_active_count(
    world, hiring_manager
):
    openings = your_openings(hiring_manager)

    assert [(o.title, o.active_count) for o in openings] == [
        ("Backend Developer", 1),
        ("QA Analyst", 1),
    ]


def test_applicants_on_your_openings_are_in_progress_and_latest_first(
    world, hiring_manager, recruiter
):
    move_application(world["cy"], Stage.SCREENING, by=recruiter)  # Cy is now the latest

    applicants = applicants_on_your_openings(hiring_manager)

    assert [a.candidate.first_name for a in applicants] == ["Cy", "Ann"]
    assert applicants_on_your_openings(hiring_manager, limit=1) == applicants[:1]


def test_recent_work_is_the_users_own_stage_changes_newest_first(world, recruiter):
    work = recent_work(recruiter)

    assert [(c.application.candidate.first_name, c.from_stage, c.to_stage) for c in work] == [
        ("Ben", Stage.APPLIED, Stage.REJECTED),
        ("Ann", Stage.APPLIED, Stage.SCREENING),
        ("Ann", "", Stage.APPLIED),
    ]


def test_the_pipeline_snapshot_counts_open_openings_at_every_active_stage(world):
    assert [(row.stage, row.count) for row in pipeline_snapshot()] == [
        (Stage.APPLIED, 1),  # Dee; Cy's opening is closed
        (Stage.SCREENING, 1),
        (Stage.INTERVIEW, 0),
        (Stage.FINAL_REVIEW, 0),
        (Stage.OFFER, 0),
    ]


def test_your_attention_lists_only_what_is_assigned_to_the_user(world, hiring_manager, admin):
    assert [item.opening.title for item in your_attention(hiring_manager)] == ["QA Analyst"]
    # The Admin may decide for QA Analyst too, but it isn't assigned to them.
    assert your_attention(admin) == []


def test_the_home_page_shows_a_managers_openings_applicants_and_decisions(
    client, world, hiring_manager
):
    client.force_login(hiring_manager)

    html = page(client.get(reverse("accounts:home")))

    assert html.count('data-testid="home-opening"') == 2
    assert html.count('data-testid="home-applicant"') == 2
    item = html.split('data-testid="home-attention-item"')[1].split("</li>")[0]
    assert "QA Analyst" in item
    assert "Closed · 1 still in progress" in item
    assert f"/openings/{world['qa'].pk}/#closure" in item
    assert 'data-testid="home-work-empty"' in html  # the manager made no moves
    assert 'data-testid="home-pipeline"' in html


def test_interviewers_see_the_shared_numbers_without_sections_of_their_own(
    client, world, interviewer
):
    client.force_login(interviewer)

    html = page(client.get(reverse("accounts:home")))

    assert 'data-testid="home-pipeline"' in html
    assert 'data-testid="stat-open-openings"' in html
    for section in ("home-attention", "home-openings", "home-applicants", "home-work"):
        assert f'data-testid="{section}"' not in html
    assert 'data-testid="quick-add-candidate"' not in html


@pytest.mark.parametrize(
    ("role", "actions"),
    [
        ("admin", {"quick-add-candidate", "quick-record-application", "quick-new-opening"}),
        ("recruiter", {"quick-add-candidate", "quick-record-application", "quick-new-opening"}),
        ("hiring_manager", {"quick-new-opening"}),
        ("interviewer", set()),
    ],
)
def test_quick_actions_match_what_the_role_may_do(request, client, role, actions):
    client.force_login(request.getfixturevalue(role))

    html = page(client.get(reverse("accounts:home")))

    every = {"quick-add-candidate", "quick-record-application", "quick-new-opening"}
    assert {a for a in every if f'data-testid="{a}"' in html} == actions


def test_a_recruiters_recent_work_shows_recorded_and_moved_applications(client, world, recruiter):
    client.force_login(recruiter)

    html = " ".join(page(client.get(reverse("accounts:home"))).split())

    assert html.count('data-testid="home-work-item"') == 3
    assert "from Applied to Rejected" in html
    assert "as Applied" in html


def test_the_four_lists_sit_attention_openings_then_applicants_work(client, world, recruiter):
    client.force_login(recruiter)

    html = page(client.get(reverse("accounts:home")))

    order = ["home-attention", "home-openings", "home-applicants", "home-work", "home-pipeline"]
    positions = [html.index(f'data-testid="{section}"') for section in order]
    assert positions == sorted(positions)
    grid = html.split('data-testid="home-grid"')[1].split('data-testid="home-pipeline"')[0]
    assert all(f'data-testid="{section}"' in grid for section in order[:4])


@pytest.mark.parametrize(("count", "hidden"), [(0, 0), (5, 0), (6, 1), (9, 4)])
def test_a_fold_hides_the_rows_past_five(count, hidden):
    fold = Fold(list(range(count)))

    assert fold.fold_at == FOLD_AT == 5
    assert fold.hidden_count == hidden
    assert len(fold) == count
    assert list(fold) == list(range(count))


def section(html: str, name: str) -> str:
    return html.split(f'data-testid="{name}"')[1].split("</section>")[0]


def test_a_list_of_more_than_five_folds_behind_a_show_more_toggle(
    client, make_opening, hiring_manager
):
    for number in range(7):
        make_opening(f"Opening {number}", hiring_manager)
    client.force_login(hiring_manager)

    html = section(page(client.get(reverse("accounts:home"))), "home-openings")

    assert html.count('data-testid="home-opening"') == 7  # every row is on the page
    assert html.count("data-beyond-fold") == 2  # the last two are folded away
    assert "Show 2 more" in html
    assert "Show less" in html
    assert 'aria-expanded="false"' in html


def test_a_list_of_five_or_fewer_has_no_toggle(client, make_opening, hiring_manager):
    for number in range(5):
        make_opening(f"Opening {number}", hiring_manager)
    client.force_login(hiring_manager)

    html = section(page(client.get(reverse("accounts:home"))), "home-openings")

    assert html.count('data-testid="home-opening"') == 5
    assert "data-beyond-fold" not in html
    assert 'data-testid="fold-toggle"' not in html


def test_every_needs_attention_item_is_listed_and_counted(make_opening, hiring_manager, apply):
    for number in range(7):
        opening = make_opening(f"Closed {number}", hiring_manager)
        apply(f"Cand{number}", opening)
        JobOpening.objects.filter(pk=opening.pk).update(status=JobOpening.Status.CLOSED)

    assert len(your_attention(hiring_manager)) == 7


def test_every_home_list_row_has_the_same_shape_and_height(client, world, recruiter, make_opening):
    make_opening("Ops", recruiter)  # the recruiter has openings, applicants and work too
    client.force_login(recruiter)

    html = page(client.get(reverse("accounts:home")))

    rows = [
        chunk.split(">")[0]
        for name in ("home-attention-item", "home-opening", "home-applicant", "home-work-item")
        for chunk in html.split("<li ")[1:]
        if f'data-testid="{name}"' in chunk.split(">")[0]
    ]
    assert len(rows) >= 3
    assert all("min-h-18 items-center" in row and "px-3 py-2.5" in row for row in rows)
