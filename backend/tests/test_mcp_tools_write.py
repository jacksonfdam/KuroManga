"""The tools that change something.

The bound on download_chapters is the point of most of this file: the endpoint
behind it reads two null bounds as "every missing chapter", which is what once
queued tens of thousands of chapters and filled fifteen gigabytes.
"""

import pytest

from app.mcp import tools
from tests.test_mcp_tools_read import FakeApi

pytestmark = pytest.mark.asyncio


async def test_confirming_a_mapping_returns_the_discovery_job_it_started():
    api = FakeApi({"/api/series/7/mapping": {"ok": True, "job_id": 11}})
    answer = await tools.confirm_mapping(api, 7, "https://mangadex.org/title/a")
    assert api.calls == [
        ("POST", "/api/series/7/mapping", {"source_url": "https://mangadex.org/title/a"})
    ]
    assert answer == {"ok": True, "job_id": 11}


async def test_a_download_states_both_bounds_even_when_only_one_was_asked_for():
    api = FakeApi({"/api/series/7/download": {"ok": True, "queued": 20}})
    answer = await tools.download_chapters(api, 7, from_chapter=1)
    sent = api.calls[0][2]
    assert sent["from_chapter"] == 1
    assert sent["to_chapter"] == 1 + tools.MAX_CHAPTER_SPAN
    assert answer["queued"] == 20


async def test_a_span_wider_than_the_cap_is_capped_and_says_so():
    api = FakeApi({"/api/series/7/download": {"ok": True, "queued": 50}})
    answer = await tools.download_chapters(api, 7, from_chapter=1, to_chapter=9000)
    assert api.calls[0][2]["to_chapter"] == 1 + tools.MAX_CHAPTER_SPAN
    assert answer["capped"] is True
    assert "set_follow" in answer["note"]


async def test_a_span_inside_the_cap_is_sent_as_asked():
    api = FakeApi({"/api/series/7/download": {"ok": True, "queued": 5}})
    answer = await tools.download_chapters(api, 7, from_chapter=10, to_chapter=14)
    assert api.calls[0][2] == {"from_chapter": 10.0, "to_chapter": 14.0}
    assert answer["capped"] is False


async def test_a_backwards_range_is_refused_rather_than_queueing_nothing():
    answer = await tools.download_chapters(FakeApi({}), 7, from_chapter=40, to_chapter=10)
    assert answer["error"] == "bad_range"


async def test_following_a_series_queues_what_is_already_missing():
    api = FakeApi({"/api/series/7/auto-download": {"ok": True, "auto_download": True, "queued": 320}})
    answer = await tools.set_follow(api, 7, True)
    assert api.calls[0][2] == {"enabled": True}
    assert answer == {"ok": True, "auto_download": True, "queued": 320}


def _settings(providers=("mal", "anilist", "mangabaka")):
    return {
        "values": {},
        "providers": {name: {"uses_oauth": True, "connected": True} for name in providers},
        "library_path": "/manga",
        "sources": {},
    }


async def test_a_sync_asks_the_api_which_providers_exist():
    api = FakeApi({"/api/settings": _settings(), "/api/sync/anilist": {"ok": True, "job_id": 3}})
    answer = await tools.sync_lists(api, "anilist")
    assert [call[1] for call in api.calls] == ["/api/settings", "/api/sync/anilist"]
    assert answer["job_id"] == 3


async def test_a_provider_the_api_does_not_report_is_refused_by_name():
    api = FakeApi({"/api/settings": _settings()})
    answer = await tools.sync_lists(api, "kitsu")
    assert answer["error"] == "unknown_provider"
    assert answer["providers"] == ["anilist", "mal", "mangabaka"]


async def test_a_provider_added_later_is_accepted_without_a_change_here():
    api = FakeApi(
        {
            "/api/settings": _settings(("mal", "anilist", "mangabaka", "mangadex")),
            "/api/sync/mangadex": {"ok": True, "job_id": 9},
        }
    )
    assert (await tools.sync_lists(api, "mangadex"))["job_id"] == 9
