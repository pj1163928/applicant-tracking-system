"""What the home page shows the signed-in user: their openings, their applicants, their work.

Every section is a query here, so the view stays thin and the page counts
with the database instead of loading every record. "Yours" always means the
openings the user is the designated authority of; ownership changes what the
home page puts first, never what anyone may see.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from django.db.models import Count

from accounts.roles import AnyUser
from applications.models import Application, StageChange
from applications.stages import ACTIVE_STAGES, Stage
from notifications.attention import (
    AttentionItem,
    RestoreItem,
    closures_awaiting_decision,
    restores_awaiting_choice,
)
from openings.models import JobOpening
from openings.scopes import MINE

# How many rows the longer home-page lists (applicants, recent work) load at most.
LIST_LIMIT = 20
# How many rows each home-page section shows before folding the rest behind "Show more".
FOLD_AT = 5


@dataclass(frozen=True)
class Fold:
    """One home-page list: its rows, of which the first ``fold_at`` show until it is expanded.

    The page marks the rest ``data-beyond-fold``, and its toggle says how many
    more there are (``hidden_count``).
    """

    items: Sequence
    fold_at: int = FOLD_AT

    @property
    def hidden_count(self) -> int:
        return max(len(self.items) - self.fold_at, 0)

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self):
        return iter(self.items)


@dataclass(frozen=True)
class HomeStats:
    """The numbers across the top of the home page.

    ``open_openings`` and ``in_progress`` (applications at an active stage, on
    any opening) are everyone's; ``your_openings`` and ``your_in_progress``
    count the openings the user is the designated authority of.
    """

    open_openings: int
    in_progress: int
    your_openings: int
    your_in_progress: int


def home_stats(user: AnyUser) -> HomeStats:
    """Return the home page's numbers for ``user``, in four counting queries."""
    active = Application.objects.filter(stage__in=ACTIVE_STAGES)
    return HomeStats(
        open_openings=JobOpening.objects.accepting_applications().count(),
        in_progress=active.count(),
        your_openings=JobOpening.objects.in_scope(MINE, user).count(),
        your_in_progress=active.filter(opening__designated_authority=user).count(),
    )


def your_openings(user: AnyUser) -> list[JobOpening]:
    """Return the openings ``user`` is the designated authority of, open first, then by title.

    Each is annotated with ``active_count``, its applications still in progress.
    """
    return list(
        JobOpening.objects.in_scope(MINE, user)
        .with_active_count()
        .open_first()
        .select_related("designated_authority")
    )


def applicants_on_your_openings(user: AnyUser, *, limit: int = LIST_LIMIT) -> list[Application]:
    """Return up to ``limit`` applications in progress on ``user``'s openings, latest first.

    "Latest activity" is the application's ``updated_at``, which every move changes.
    """
    return list(
        Application.objects.filter(opening__designated_authority=user, stage__in=ACTIVE_STAGES)
        .select_related("candidate", "opening")
        .order_by("-updated_at", "-pk")[:limit]
    )


def recent_work(user: AnyUser, *, limit: int = LIST_LIMIT) -> list[StageChange]:
    """Return ``user``'s latest ``limit`` stage changes, newest first.

    That includes the first row of each application they recorded (no stage →
    Applied) and any closure or reopening moves made in their name.
    """
    return list(
        StageChange.objects.filter(changed_by=user)
        .select_related("application__candidate", "application__opening")
        .order_by("-changed_at", "-pk")[:limit]
    )


def your_attention(user: AnyUser) -> list[AttentionItem | RestoreItem]:
    """Return every Needs attention item assigned to ``user`` as designated authority.

    The same items the Needs attention panel lists under "Assigned to you".
    """
    items = closures_awaiting_decision(user) + restores_awaiting_choice(user)
    return [item for item in items if item.assigned_to_you]


@dataclass(frozen=True)
class StageCount:
    """How many applications on open openings are at one active stage."""

    stage: Stage
    count: int


def pipeline_snapshot() -> list[StageCount]:
    """Return how many applications on open openings are at each active stage, in pipeline order.

    Every active stage is listed, with 0 where nobody is at it. One query.
    """
    counts = dict(
        Application.objects.filter(
            opening__in=JobOpening.objects.accepting_applications(), stage__in=ACTIVE_STAGES
        )
        .order_by()
        .values_list("stage")
        .annotate(count=Count("pk"))
    )
    return [StageCount(stage, counts.get(stage, 0)) for stage in ACTIVE_STAGES]
