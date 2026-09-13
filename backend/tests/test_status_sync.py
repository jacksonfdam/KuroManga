import pytest

from app.discovery.status_sync import anilist_status, mal_status, mangadex_status
from app.enums import ListStatus


@pytest.mark.parametrize(
    "status,mal,anilist,mangadex",
    [
        (ListStatus.READING, "reading", "CURRENT", "reading"),
        (ListStatus.PLAN_TO_READ, "plan_to_read", "PLANNING", "plan_to_read"),
        (ListStatus.COMPLETED, "completed", "COMPLETED", "completed"),
        (ListStatus.ON_HOLD, "on_hold", "PAUSED", "on_hold"),
        (ListStatus.DROPPED, "dropped", "DROPPED", "dropped"),
    ],
)
def test_every_status_has_a_word_in_every_dialect(status, mal, anilist, mangadex):
    assert mal_status(status) == mal
    assert anilist_status(status) == anilist
    assert mangadex_status(status) == mangadex
