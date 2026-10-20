"""The eight hiring stages an application moves through, and the rules for moving between them.

A pure module: every function here takes stages only. None of them reads the
database, a request or a user, so the rules can be tested and reused anywhere.
Who may make a move is decided separately, in ``accounts.permissions``.
"""

from dataclasses import dataclass

from django.db import models


class Stage(models.TextChoices):
    """Every stage, in pipeline order. Hired, Rejected and Withdrawn are terminal."""

    APPLIED = "applied", "Applied"
    SCREENING = "screening", "Screening"
    INTERVIEW = "interview", "Interview"
    FINAL_REVIEW = "final_review", "Final Review"
    OFFER = "offer", "Offer"
    HIRED = "hired", "Hired"
    REJECTED = "rejected", "Rejected"
    WITHDRAWN = "withdrawn", "Withdrawn"


# Still in progress: any of these can move to any other, or to Rejected or Withdrawn.
ACTIVE_STAGES: tuple[Stage, ...] = (
    Stage.APPLIED,
    Stage.SCREENING,
    Stage.INTERVIEW,
    Stage.FINAL_REVIEW,
    Stage.OFFER,
)
# Ended, but can be reopened to an active stage. The board collapses these to a count.
CLOSED_STAGES: tuple[Stage, ...] = (Stage.REJECTED, Stage.WITHDRAWN)
# The forward line. A move one step along it is routine and needs no note.
PIPELINE: tuple[Stage, ...] = (*ACTIVE_STAGES, Stage.HIRED)

# Every legal move: each stage, and the stages it may move to. Hired is reachable
# only from Offer and is final.
ALLOWED_TRANSITIONS: dict[Stage, frozenset[Stage]] = {
    **{
        stage: frozenset({*ACTIVE_STAGES, *CLOSED_STAGES} - {stage})
        | ({Stage.HIRED} if stage == Stage.OFFER else set())
        for stage in ACTIVE_STAGES
    },
    Stage.HIRED: frozenset(),
    **{stage: frozenset(ACTIVE_STAGES) for stage in CLOSED_STAGES},
}


def can_move(from_stage: str, to_stage: str) -> bool:
    """Return True if the transitions table allows a move from ``from_stage`` to ``to_stage``.

    Moving to the stage an application is already at is never a move.
    Unknown stages are never allowed.
    """
    return to_stage in ALLOWED_TRANSITIONS.get(from_stage, frozenset())


def requires_note(from_stage: str, to_stage: str) -> bool:
    """Return True if this legal move can't be made without a note.

    Skips, backward moves and reopens need one. A one-step forward move doesn't,
    and a note on Rejected or Withdrawn is optional (see ``prompts_for_note``).
    Raises ``ValueError`` for a move ``can_move()`` refuses.
    """
    return move_kind(from_stage, to_stage) in (SKIP, BACK, REOPEN)


def prompts_for_note(from_stage: str, to_stage: str) -> bool:
    """Return True if this legal move asks for a note before it is made, required or optional.

    That is every move that ``requires_note()``, plus Rejected and Withdrawn,
    where the note is optional. Raises ``ValueError`` for a move ``can_move()``
    refuses.
    """
    return requires_note(from_stage, to_stage) or to_stage in CLOSED_STAGES


FORWARD, SKIP, BACK, REOPEN, CLOSE = "forward", "skip", "back", "reopen", "close"
# Where moving into these stages also needs ``accounts.permissions.can_make_offer``.
OFFER_STAGES: tuple[Stage, ...] = (Stage.OFFER, Stage.HIRED)


def move_kind(from_stage: str, to_stage: str) -> str:
    """Name this legal move: ``FORWARD`` (one step), ``SKIP``, ``BACK``, ``REOPEN`` or ``CLOSE``.

    ``CLOSE`` is a move into Rejected or Withdrawn. Raises ``ValueError`` for a
    move ``can_move()`` refuses.
    """
    _check_legal(from_stage, to_stage)
    if to_stage in CLOSED_STAGES:
        return CLOSE
    if from_stage in CLOSED_STAGES:
        return REOPEN
    step = PIPELINE.index(to_stage) - PIPELINE.index(from_stage)
    return FORWARD if step == 1 else SKIP if step > 1 else BACK


def skipped_stages(from_stage: str, to_stage: str) -> list[Stage]:
    """Return the stages a ``SKIP`` passes over, in order; an empty list for any other move."""
    if to_stage in CLOSED_STAGES or from_stage in CLOSED_STAGES:
        return []
    if from_stage not in PIPELINE or to_stage not in PIPELINE:
        return []
    return list(PIPELINE[PIPELINE.index(from_stage) + 1 : PIPELINE.index(to_stage)])


@dataclass(frozen=True)
class MoveTarget:
    """One entry in a card's Move menu: a stage it may move to, and what that move asks for."""

    stage: Stage
    kind: str
    requires_note: bool
    prompts_for_note: bool

    @property
    def label(self) -> str:
        return self.stage.label


def move_targets(from_stage: str, *, may_offer: bool) -> list[MoveTarget]:
    """Return the legal moves from ``from_stage``, in pipeline order, for a card's Move menu.

    Offer and Hired are left out unless ``may_offer`` (the caller works it out
    with ``accounts.permissions.can_make_offer``). A Hired card has none.
    """
    return [
        MoveTarget(
            stage=to,
            kind=move_kind(from_stage, to),
            requires_note=requires_note(from_stage, to),
            prompts_for_note=prompts_for_note(from_stage, to),
        )
        for to in Stage
        if can_move(from_stage, to) and (may_offer or to not in OFFER_STAGES)
    ]


def withholds_offer_targets(from_stage: str, *, may_offer: bool) -> bool:
    """Return True if ``move_targets`` leaves out Offer or Hired only because of ``may_offer``."""
    return not may_offer and any(can_move(from_stage, to) for to in OFFER_STAGES)


def _check_legal(from_stage: str, to_stage: str) -> None:
    if not can_move(from_stage, to_stage):
        raise ValueError(f"{from_stage!r} → {to_stage!r} is not a legal move.")
