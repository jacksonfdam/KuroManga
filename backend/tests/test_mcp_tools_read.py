"""The read tools, against a fake API.

Same shape as the other pure-edge tests in this suite: the API is a recorded
answer, so what is under test is the record each tool builds and the size of it.
"""

import json

import pytest

from app.mcp import tools

pytestmark = pytest.mark.asyncio


class FakeApi:
    """Answers whatever the test registered, and remembers what was asked."""

    def __init__(self, routes: dict[str, object]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, str, object]] = []

    async def get(self, path, params=None):
        self.calls.append(("GET", path, params))
        return self.routes[path]

    async def post(self, path, json=None):
        self.calls.append(("POST", path, json))
        return self.routes[path]


def fat_series(series_id: int) -> dict:
    """A row as `GET /api/series` really answers, Library fields and all."""
    return {
        "id": series_id,
        "title": f"Series {series_id}",
        "slug": f"series-{series_id}",
        "cover_url": "https://example.test/cover.jpg",
        "source_site": "mangadex",
        "source_url": "https://mangadex.org/title/x",
        "providers": ["anilist", "mal"],
        "writable": True,
        "downloaded": 12,
        "known": 40,
        "in_flight": 0,
        "failed": 0,
        "total_chapters": 40,
        "auto_download": False,
        "state": "mapped",
        "status": "reading",
        "progress": 11,
        "updated_at": "2026-09-01T00:00:00+00:00",
        "komga_series_id": "0ABC",
        "score": 84,
        "genres": ["Action", "Drama", "Adventure"],
        "format": "MANGA",
        "demographic": "shounen",
        "description": "A long synopsis that the grid shows on hover. " * 8,
    }


async def test_list_series_states_only_the_fields_a_decision_needs():
    api = FakeApi({"/api/series": [fat_series(1)]})
    answer = await tools.list_series(api)
    assert set(answer["series"][0]) == {
        "id",
        "title",
        "state",
        "downloaded",
        "known",
        "total_chapters",
        "auto_download",
    }


async def test_list_series_passes_the_state_filter_to_the_api():
    api = FakeApi({"/api/series": []})
    await tools.list_series(api, state="needs_review")
    assert api.calls == [("GET", "/api/series", {"state": "needs_review"})]


async def test_an_unknown_state_is_refused_by_name_not_answered_with_nothing():
    answer = await tools.list_series(FakeApi({}), state="mapepd")
    assert answer["ok"] is False
    assert answer["error"] == "unknown_state"


async def test_a_library_of_three_hundred_still_fits_the_budget():
    api = FakeApi({"/api/series": [fat_series(n) for n in range(300)]})
    answer = await tools.list_series(api, limit=50)
    assert len(json.dumps(answer)) <= tools.RESPONSE_BUDGET
    assert answer["total"] == 300
    assert answer["truncated"] is True
    assert answer["returned"] < 50


async def test_the_review_queue_lists_what_is_waiting():
    api = FakeApi(
        {
            "/api/series/review/queue": {
                "total": 2,
                "items": [
                    {"id": 7, "title": "Berserk", "cover_url": "x", "candidate_count": 3},
                    {"id": 8, "title": "Vinland Saga", "cover_url": "y", "candidate_count": 0},
                ],
            }
        }
    )
    answer = await tools.review_queue(api)
    assert answer["total"] == 2
    assert answer["pending"][0] == {"id": 7, "title": "Berserk", "candidates": 3}


async def test_one_series_answers_with_its_candidates():
    api = FakeApi({"/api/series/7/candidates": _candidates()})
    answer = await tools.review_queue(api, series_id=7)
    assert answer["candidates"][0]["source_url"] == "https://mangadex.org/title/a"
    assert answer["candidates"][0]["score"] == 0.914


async def test_a_refresh_queues_a_search_and_says_the_list_is_still_the_old_one():
    api = FakeApi(
        {"/api/series/7/candidates": _candidates(), "/api/series/7/search": {"ok": True, "job_id": 42}}
    )
    answer = await tools.review_queue(api, series_id=7, refresh=True)
    assert ("POST", "/api/series/7/search", None) in api.calls
    assert answer["search_job_id"] == 42
    assert "call again" in answer["note"]


async def test_a_refresh_without_a_series_is_refused():
    answer = await tools.review_queue(FakeApi({}), refresh=True)
    assert answer["error"] == "series_required"


def _candidates():
    return {
        "series": {"id": 7, "title": "Berserk", "titles": [], "english": [], "romaji": []},
        "candidates": [
            {
                "id": 1,
                "source_site": "mangadex",
                "source_url": "https://mangadex.org/title/a",
                "title": "Berserk",
                "cover_url": "https://example.test/a.jpg",
                "chapter_count": 401,
                "year": 1989,
                "score": 0.9142,
            }
        ],
    }


def _dashboard():
    return {
        "queue": {"pending": 3, "leased": 1, "done": 900, "failed": 2},
        "worker": {"state": "ok", "running": 1, "expired_leases": 0, "last_finished_at": None},
        "downloads": {"in_flight": 1, "queued": 12, "failed_24h": 2, "sources": ["mangadex"]},
        "mappings": {"pending": 5, "with_candidates": 4},
        "discovery": {"new": 0, "new_today": 0, "providers": []},
        "continue_reading": [{"id": n} for n in range(8)],
        "suggestions": [{"id": n} for n in range(4)],
        "activity": {"running": [], "recent": []},
        "storage": {"used": 1, "free": 2},
        "cron": {},
    }


def _failed_job(job_id: int) -> dict:
    return {
        "id": job_id,
        "type": "download_chapter",
        "lane": "download",
        "state": "failed",
        "attempts": 3,
        "max_attempts": 3,
        "last_error": "HTTP 503 from the source, " * 20,
        "permanent": False,
        "series_id": 7,
        "series_title": "Berserk",
        "chapter_number": 12.0,
        "chapter_title": "The Black Swordsman",
        "pct": None,
        "last_message": "giving up",
        "created_at": "2026-09-01T00:00:00+00:00",
        "started_at": None,
        "finished_at": None,
    }


async def test_jobs_status_reads_the_dashboard_rather_than_composing_two_counts():
    api = FakeApi({"/api/dashboard": _dashboard(), "/api/jobs": [_failed_job(1)]})
    answer = await tools.jobs_status(api)
    assert [call[1] for call in api.calls] == ["/api/dashboard", "/api/jobs"]
    assert answer["queue"]["failed"] == 2
    assert answer["worker"]["state"] == "ok"
    assert answer["awaiting_review"] == 5


async def test_a_failure_is_named_without_its_whole_traceback():
    api = FakeApi({"/api/dashboard": _dashboard(), "/api/jobs": [_failed_job(n) for n in range(5)]})
    answer = await tools.jobs_status(api)
    assert len(answer["failures"][0]["error"]) == tools.ERROR_EXCERPT
    assert len(json.dumps(answer)) <= tools.RESPONSE_BUDGET
