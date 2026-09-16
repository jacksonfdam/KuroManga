"""One item waiting on a decision, and how far it is from being done.

Discovery, Unmatched and Review were three screens asking three stages of one
question. An item here says what it still owes, and the rank is how the feed
decides what to show first - which matters more than the merge itself, because
most of the list needs a manual search and would otherwise bury everything that
is one click away.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Need(StrEnum):
    """A step still owed before this is a series that can download."""

    MATCH = "match"
    STATUS = "status"
    SOURCE = "source"


@dataclass
class DiscoverItem:
    kind: str
    id: int
    series_id: int | None
    title: str
    cover_url: str | None
    why: str
    needs: list[Need]
    candidates: list[dict[str, Any]] = field(default_factory=list)
    #: A source good enough to accept without a decision. Borrowed from
    #: routes_discovery.confident rather than re-derived, so the feed and the
    #: screen it replaces cannot disagree about what confident means.
    confident: bool = False
    rank_score: float = 0.0
    candidate_count: int = 0
    #: The origin anime was finished. Only meaningful for items needing a match.
    finished: bool = False


def rank_of(item: DiscoverItem) -> int:
    """Distance to done, lowest first.

    Rank 3 sits below rank 2 on purpose. An item with one step left and no
    candidates at all looks like the easiest row in the list and is the hardest:
    it needs a URL found and pasted by hand. Ranking purely by steps remaining
    would float every dead end to the top.
    """
    if Need.MATCH in item.needs:
        return 4
    if item.confident:
        return 1
    return 2 if item.candidate_count > 0 else 3


def sort_key(item: DiscoverItem) -> tuple[int, int, float, str]:
    """Rank first, then whatever signal each kind already carries.

    `finished` separates only the items that need a search; everywhere else it
    is false and contributes nothing. Title breaks the last tie so two loads of
    the same feed never disagree about the order.
    """
    return (
        rank_of(item),
        0 if item.finished else 1,
        -item.rank_score,
        item.title.lower(),
    )
