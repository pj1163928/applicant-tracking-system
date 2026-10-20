"""The pure stage rules: the transitions table, and when a move needs or asks for a note.

This file has no ``django_db`` mark on purpose: pytest-django fails any test
here that touches the database. The rules take stages only, never a user or a
request, so who may make a move is tested in ``accounts`` instead.
"""

import pytest

from applications.stages import (
    BACK,
    CLOSE,
    FORWARD,
    REOPEN,
    SKIP,
    Stage,
    can_move,
    move_kind,
    move_targets,
    prompts_for_note,
    requires_note,
    skipped_stages,
    withholds_offer_targets,
)

AP, SC, IN, FR, OF, HI, RE, WD = (
    Stage.APPLIED,
    Stage.SCREENING,
    Stage.INTERVIEW,
    Stage.FINAL_REVIEW,
    Stage.OFFER,
    Stage.HIRED,
    Stage.REJECTED,
    Stage.WITHDRAWN,
)
ACTIVE = {AP, SC, IN, FR, OF}

# The complete transitions matrix from the PRD, written out by hand: each stage, and
# every stage it may move to. Any active stage moves to any other active stage, Rejected
# or Withdrawn; Hired is reachable only from Offer and is final; Rejected and Withdrawn
# reopen to an active stage only.
EXPECTED_MATRIX: dict[Stage, set[Stage]] = {
    AP: {SC, IN, FR, OF, RE, WD},
    SC: {AP, IN, FR, OF, RE, WD},
    IN: {AP, SC, FR, OF, RE, WD},
    FR: {AP, SC, IN, OF, RE, WD},
    OF: {AP, SC, IN, FR, HI, RE, WD},
    HI: set(),
    RE: {AP, SC, IN, FR, OF},
    WD: {AP, SC, IN, FR, OF},
}

# For every legal move: (no note, optional note, required note). A one-step forward move
# needs no note; Rejected and Withdrawn ask for an optional one; skips, backward moves
# and reopens can't happen without one.
NOTE_RULES: dict[Stage, tuple[set[Stage], set[Stage], set[Stage]]] = {
    AP: ({SC}, {RE, WD}, {IN, FR, OF}),
    SC: ({IN}, {RE, WD}, {AP, FR, OF}),
    IN: ({FR}, {RE, WD}, {AP, SC, OF}),
    FR: ({OF}, {RE, WD}, {AP, SC, IN}),
    OF: ({HI}, {RE, WD}, {AP, SC, IN, FR}),
    HI: (set(), set(), set()),
    RE: (set(), set(), {AP, SC, IN, FR, OF}),
    WD: (set(), set(), {AP, SC, IN, FR, OF}),
}


def test_can_move_matches_the_complete_transition_matrix():
    actual = {from_stage: {to for to in Stage if can_move(from_stage, to)} for from_stage in Stage}

    assert actual == EXPECTED_MATRIX


@pytest.mark.parametrize("stage", list(Stage))
def test_no_stage_can_move_to_itself(stage):
    assert can_move(stage, stage) is False


def test_terminal_stages_are_left_only_as_the_table_allows():
    # Hired is final, and only Offer leads to it.
    assert [to for to in Stage if can_move(HI, to)] == []
    assert {from_stage for from_stage in Stage if can_move(from_stage, HI)} == {OF}
    # Rejected and Withdrawn reopen to an active stage, never to Hired or to each other.
    for closed in (RE, WD):
        assert {to for to in Stage if can_move(closed, to)} == ACTIVE


def test_the_note_rules_cover_exactly_the_legal_moves():
    # A guard on the tables above, so a move can't be missing from either.
    for from_stage, (none, optional, required) in NOTE_RULES.items():
        assert none | optional | required == EXPECTED_MATRIX[from_stage]
        assert not (none & optional or none & required or optional & required)


@pytest.mark.parametrize("from_stage", list(Stage))
def test_requiring_a_note_and_prompting_for_one_are_separate_rules(from_stage):
    none, optional, required = NOTE_RULES[from_stage]
    for to in none:
        assert (requires_note(from_stage, to), prompts_for_note(from_stage, to)) == (False, False)
    for to in optional:
        assert (requires_note(from_stage, to), prompts_for_note(from_stage, to)) == (False, True)
    for to in required:
        assert (requires_note(from_stage, to), prompts_for_note(from_stage, to)) == (True, True)


@pytest.mark.parametrize("from_stage", sorted(ACTIVE))
@pytest.mark.parametrize("to", [RE, WD])
def test_rejecting_or_withdrawing_prompts_for_an_optional_note(from_stage, to):
    assert prompts_for_note(from_stage, to) is True
    assert requires_note(from_stage, to) is False


@pytest.mark.parametrize(("from_stage", "to"), [(AP, AP), (AP, HI), (HI, RE), (RE, WD), (WD, HI)])
def test_the_note_rules_refuse_to_judge_an_illegal_move(from_stage, to):
    with pytest.raises(ValueError):
        requires_note(from_stage, to)
    with pytest.raises(ValueError):
        prompts_for_note(from_stage, to)


def test_move_kind_names_each_kind_of_move():
    assert [move_kind(AP, to) for to in (SC, IN, RE)] == [FORWARD, SKIP, CLOSE]
    assert [move_kind(OF, HI), move_kind(FR, SC), move_kind(WD, IN)] == [FORWARD, BACK, REOPEN]


def test_the_move_menu_lists_every_legal_target_in_pipeline_order():
    targets = move_targets(FR, may_offer=True)

    assert [t.stage for t in targets] == [AP, SC, IN, OF, RE, WD]
    assert [(t.requires_note, t.prompts_for_note) for t in targets] == [
        (True, True),
        (True, True),
        (True, True),
        (False, False),  # Final Review → Offer is one step forward
        (False, True),
        (False, True),
    ]
    assert withholds_offer_targets(FR, may_offer=True) is False


@pytest.mark.parametrize(("from_stage", "hidden"), [(FR, {OF}), (OF, {HI}), (RE, {OF})])
def test_the_move_menu_leaves_out_offer_and_hired_without_offer_authority(from_stage, hidden):
    shown = {t.stage for t in move_targets(from_stage, may_offer=False)}

    assert shown == EXPECTED_MATRIX[from_stage] - hidden
    assert withholds_offer_targets(from_stage, may_offer=False) is True


def test_a_hired_card_has_no_moves():
    assert move_targets(HI, may_offer=True) == []
    assert withholds_offer_targets(HI, may_offer=False) is False


def test_skipped_stages_lists_what_a_skip_passes_over():
    assert skipped_stages(AP, FR) == [SC, IN]
    assert skipped_stages(AP, SC) == []
    assert skipped_stages(FR, AP) == []
    assert skipped_stages(RE, OF) == []
