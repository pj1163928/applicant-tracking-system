"""Each stage's icon, on the pipeline board and the home page's pipeline snapshot."""

import pytest
from django.urls import reverse

from applications.stages import ACTIVE_STAGES, Stage
from applications.templatetags.stage_tags import STAGE_ICONS, stage_icon
from config.templatetags.icons import ICON_DIR, icon


def test_every_stage_has_its_own_icon_and_the_icon_file_exists():
    assert set(STAGE_ICONS) == set(Stage)
    assert len(set(STAGE_ICONS.values())) == len(Stage)  # no two stages share one
    assert all((ICON_DIR / f"{name}.svg").is_file() for name in STAGE_ICONS.values())


def test_stage_icon_accepts_the_stored_value():
    assert stage_icon("final_review") == "clipboard-check"


def column_heading(html: str, stage: str) -> str:
    return html.split(f'data-testid="column-{stage}"')[1].split(f'id="count-{stage}"')[0]


@pytest.mark.django_db
def test_board_columns_and_the_home_snapshot_show_each_stages_icon(client, recruiter, make_opening):
    opening = make_opening("Backend Developer", recruiter)
    client.force_login(recruiter)

    board = client.get(reverse("openings:board", args=[opening.pk])).content.decode()
    home = client.get(reverse("accounts:home")).content.decode()

    for stage in Stage:
        assert icon(STAGE_ICONS[stage], "size-4 opacity-70") in column_heading(board, stage)
    for stage in ACTIVE_STAGES:
        box = home.split(f'data-testid="pipeline-{stage}"')[1].split("</li>")[0]
        assert icon(STAGE_ICONS[stage], "size-4") in box
