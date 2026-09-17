"""How the feed is ordered, which is the part that can be wrong without erroring.

Most of the list needs a manual search before it can do anything. Get the order
wrong and the handful that are one click from done are buried, and the screen is
useless on its first day.
"""

from datetime import UTC, datetime

from app.discovery.feed import (
    DiscoverItem,
    Kind,
    Need,
    Sort,
    matching,
    ordered,
    rank_of,
    sort_key,
)


def item(**kw) -> DiscoverItem:
    base = {
        "kind": "suggestion", "id": 1, "series_id": None, "title": "A work",
        "cover_url": None, "why": "", "needs": [Need.SOURCE], "candidates": [],
        "confident": False, "rank_score": 0.0, "candidate_count": 0, "finished": False,
    }
    base.update(kw)
    return DiscoverItem(**base)


def test_a_confident_single_step_ranks_first():
    assert rank_of(item(needs=[Need.SOURCE], confident=True)) == 1


def test_an_ambiguous_single_step_ranks_second():
    assert rank_of(item(needs=[Need.SOURCE], candidate_count=3)) == 2


def test_a_dead_end_ranks_below_an_ambiguous_one():
    """It looks like one step and is the most work in the list."""
    assert rank_of(item(needs=[Need.SOURCE], candidate_count=0)) > rank_of(
        item(needs=[Need.SOURCE], candidate_count=3)
    )


def test_needing_a_search_ranks_last():
    assert rank_of(item(needs=[Need.MATCH, Need.STATUS, Need.SOURCE])) == 4


def test_the_order_is_confident_then_ambiguous_then_dead_end_then_search():
    rows = [
        item(id=4, needs=[Need.MATCH, Need.STATUS, Need.SOURCE]),
        item(id=3, needs=[Need.SOURCE], candidate_count=0),
        item(id=1, needs=[Need.SOURCE], confident=True),
        item(id=2, needs=[Need.SOURCE], candidate_count=3),
    ]
    assert [row.id for row in sorted(rows, key=sort_key)] == [1, 2, 3, 4]


def test_a_finished_anime_outranks_an_unfinished_one_among_searches():
    """Having finished an anime is the strongest signal its manga is wanted."""
    rows = [
        item(id=2, needs=[Need.MATCH], finished=False),
        item(id=1, needs=[Need.MATCH], finished=True),
    ]
    assert [row.id for row in sorted(rows, key=sort_key)] == [1, 2]


def at(day: int) -> datetime:
    return datetime(2026, 1, day, tzinfo=UTC)


def test_a_search_matches_part_of_the_title_whatever_the_case():
    rows = [item(id=1, title="Vinland Saga"), item(id=2, title="Berserk")]
    assert [row.id for row in matching(rows, q="SAGA")] == [1]


def test_no_search_keeps_everything():
    rows = [item(id=1, title="Vinland Saga"), item(id=2, title="Berserk")]
    assert len(matching(rows, q=None)) == 2


def test_a_kind_filter_keeps_only_that_kind():
    rows = [item(id=1, kind="suggestion"), item(id=2, kind="review"), item(id=3, kind="unmatched")]
    assert [row.id for row in matching(rows, kinds=[Kind.REVIEW])] == [2]


def test_two_kinds_keep_both():
    rows = [item(id=1, kind="suggestion"), item(id=2, kind="review"), item(id=3, kind="unmatched")]
    kept = matching(rows, kinds=[Kind.SUGGESTION, Kind.UNMATCHED])
    assert [row.id for row in kept] == [1, 3]


def test_an_empty_kind_filter_keeps_everything():
    """No chip selected is every chip selected, not nothing."""
    rows = [item(id=1, kind="suggestion"), item(id=2, kind="review")]
    assert len(matching(rows, kinds=[])) == 2


def test_title_sort_is_alphabetical_whatever_the_rank():
    rows = [item(id=1, title="Berserk", confident=True), item(id=2, title="Akira")]
    assert [row.id for row in ordered(rows, Sort.TITLE)] == [2, 1]


def test_title_sort_reversed_is_the_other_way_round():
    rows = [item(id=1, title="Berserk"), item(id=2, title="Akira")]
    assert [row.id for row in ordered(rows, Sort.TITLE_DESC)] == [1, 2]


def test_added_sort_is_oldest_first():
    rows = [item(id=1, added_at=at(9)), item(id=2, added_at=at(2))]
    assert [row.id for row in ordered(rows, Sort.ADDED)] == [2, 1]


def test_added_sort_reversed_is_newest_first():
    rows = [item(id=1, added_at=at(9)), item(id=2, added_at=at(2))]
    assert [row.id for row in ordered(rows, Sort.ADDED_DESC)] == [1, 2]


def test_an_item_with_no_date_sorts_last_whichever_way_the_dates_run():
    """An unmatched anime has no date to sort by, and inventing one would put
    a thousand rows in a position that means nothing."""
    rows = [item(id=1, added_at=None), item(id=2, added_at=at(2)), item(id=3, added_at=at(9))]
    assert [row.id for row in ordered(rows, Sort.ADDED)] == [2, 3, 1]
    assert [row.id for row in ordered(rows, Sort.ADDED_DESC)] == [3, 2, 1]


def test_rank_is_the_default_order():
    rows = [item(id=2, title="Akira"), item(id=1, title="Berserk", confident=True)]
    assert [row.id for row in ordered(rows, Sort.RANK)] == [1, 2]
