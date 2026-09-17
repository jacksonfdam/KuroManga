"""One item waiting on a decision, and how far it is from being done.

Discovery, Unmatched and Review were three screens asking three stages of one
question. An item here says what it still owes, and the rank is how the feed
decides what to show first - which matters more than the merge itself, because
most of the list needs a manual search and would otherwise bury everything that
is one click away.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class Kind(StrEnum):
    """Which of the three places an item came from.

    The screen shows this rather than the step owed: a reader picking a filter
    is choosing between recommendations, series missing a source and anime with
    no manga, and those are the words for it.
    """

    SUGGESTION = "suggestion"
    REVIEW = "review"
    UNMATCHED = "unmatched"


class Sort(StrEnum):
    """What the reader asked the list to be ordered by."""

    RANK = "rank"
    TITLE = "title"
    TITLE_DESC = "-title"
    ADDED = "added"
    ADDED_DESC = "-added"


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
    #: When this first appeared as something waiting. An unmatched anime has
    #: none: `anime_entry` carries only an `updated_at` the sync rewrites on
    #: every run, so there is no answer to give and none is given.
    added_at: datetime | None = None


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


def matching(
    items: Sequence[DiscoverItem],
    *,
    q: str | None = None,
    kinds: Collection[Kind] | None = None,
) -> list[DiscoverItem]:
    """The rows a search box and a row of chips leave behind.

    An empty set of kinds means every kind. No chip selected is the state the
    screen opens in, and reading it as "show nothing" would make the first
    click on a chip the only way to see anything at all.
    """
    needle = (q or "").strip().lower()
    wanted = set(kinds or ())
    return [
        item
        for item in items
        if (not needle or needle in item.title.lower())
        and (not wanted or item.kind in wanted)
    ]


def _added_key(item: DiscoverItem, *, newest_first: bool) -> tuple[int, float, str]:
    """Undated last, whichever way the dates run.

    Reversing the list would put the undated items first in one direction, and
    a thousand anime with no date is not what anyone asked to see at the top.
    So the missing case is its own leading term and never moves.
    """
    if item.added_at is None:
        return (1, 0.0, item.title.lower())
    stamp = item.added_at.timestamp()
    return (0, -stamp if newest_first else stamp, item.title.lower())


def ordered(items: Sequence[DiscoverItem], sort: Sort) -> list[DiscoverItem]:
    """Rank by default, because it is the only order that knows what is nearly done."""
    if sort is Sort.TITLE:
        return sorted(items, key=lambda item: item.title.lower())
    if sort is Sort.TITLE_DESC:
        return sorted(items, key=lambda item: item.title.lower(), reverse=True)
    if sort is Sort.ADDED:
        return sorted(items, key=lambda item: _added_key(item, newest_first=False))
    if sort is Sort.ADDED_DESC:
        return sorted(items, key=lambda item: _added_key(item, newest_first=True))
    return sorted(items, key=sort_key)
