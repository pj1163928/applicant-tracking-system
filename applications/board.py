"""The pipeline board for one opening: its columns, their cards, and each card's Move menu.

The full board and the move endpoint's partial updates both build their
columns here, so a swapped column always matches a freshly loaded one.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from accounts.permissions import can_make_offer, can_move_applications
from accounts.roles import AnyUser
from applications.models import Application
from applications.stages import (
    CLOSED_STAGES,
    MoveTarget,
    Stage,
    move_targets,
    withholds_offer_targets,
)
from openings.models import JobOpening

# A column with more cards than this shows only the newest ones until it's expanded.
FOLD_AT = 3


@dataclass
class Column:
    """One stage's column: its cards, and the Move menu every card in it shares."""

    stage: Stage
    applications: list[Application] = field(default_factory=list)
    targets: list[MoveTarget] = field(default_factory=list)
    # True when Offer or Hired is missing from ``targets`` only because the user can't make offers.
    offer_withheld: bool = False

    @property
    def collapsible(self) -> bool:
        """Rejected and Withdrawn start collapsed to a count the user can expand."""
        return self.stage in CLOSED_STAGES

    @property
    def count(self) -> int:
        return len(self.applications)

    @property
    def fold_at(self) -> int:
        """How many cards show while the column is folded."""
        return FOLD_AT

    @property
    def folded_count(self) -> int:
        """How many cards are hidden behind "+N more" while the column is folded."""
        return max(0, self.count - FOLD_AT)

    @property
    def drop_stages(self) -> str:
        """The Move menu's targets, space-separated, to highlight drop columns while dragging."""
        return " ".join(target.stage for target in self.targets)

    @property
    def note_stages(self) -> str:
        """The targets that ask for a note (required or optional), space-separated."""
        return " ".join(target.stage for target in self.targets if target.prompts_for_note)


def board_columns(
    opening: JobOpening, user: AnyUser, stages: Iterable[str] | None = None
) -> list[Column]:
    """Return ``opening``'s columns in pipeline order, each with its cards and Move menu.

    Pass ``stages`` to build only those columns, as the move endpoint does for
    the columns a move touched. Users who may not move stages (Interviewers)
    get columns with no Move targets. Cards are newest first (the most recently
    moved or recorded at the top), so a folded column shows its latest arrivals.
    """
    wanted = [stage for stage in Stage if stages is None or stage in set(stages)]
    may_move = can_move_applications(user)
    may_offer = may_move and can_make_offer(user, opening)
    cards: dict[str, list[Application]] = defaultdict(list)
    applications = (
        Application.objects.filter(opening=opening, stage__in=wanted)
        .select_related("candidate", "source")
        .order_by("-updated_at", "-pk")
    )
    for application in applications:
        cards[application.stage].append(application)
    return [
        Column(
            stage=stage,
            applications=cards[stage],
            targets=move_targets(stage, may_offer=may_offer) if may_move else [],
            offer_withheld=may_move and withholds_offer_targets(stage, may_offer=may_offer),
        )
        for stage in wanted
    ]
