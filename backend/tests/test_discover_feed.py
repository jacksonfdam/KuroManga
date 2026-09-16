"""How the feed is ordered, which is the part that can be wrong without erroring.

Most of the list needs a manual search before it can do anything. Get the order
wrong and the handful that are one click from done are buried, and the screen is
useless on its first day.
"""

from app.discovery.feed import DiscoverItem, Need, rank_of, sort_key


def item(**kw) -> DiscoverItem:
    base = dict(
        kind="suggestion", id=1, series_id=None, title="A work", cover_url=None,
        why="", needs=[Need.SOURCE], candidates=[], confident=False,
        rank_score=0.0, candidate_count=0, finished=False,
    )
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
