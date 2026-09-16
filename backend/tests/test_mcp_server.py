"""The tools as the client sees them.

Registration is worth a test of its own: a tool whose schema drifts from the
function behind it fails at call time, in a client, with no traceback here.
"""

import json

import pytest

from app.mcp import tools
from app.mcp.api import ApiError
from app.mcp.server import build
from tests.test_mcp_tools_read import (
    FakeApi,
    _candidates,
    _dashboard,
    _failed_job,
    fat_series,
)

pytestmark = pytest.mark.asyncio


async def test_the_whole_loop_is_reachable_and_nothing_else_is():
    listed = await build(FakeApi({})).list_tools()
    assert {tool.name for tool in listed} == {
        "list_series",
        "review_queue",
        "jobs_status",
        "confirm_mapping",
        "download_chapters",
        "set_follow",
        "sync_lists",
    }


async def test_every_tool_describes_itself_for_a_small_model():
    for tool in await build(FakeApi({})).list_tools():
        assert tool.description
        # Flat arguments only: a nested object is what a small model gets wrong.
        for schema in tool.input_schema["properties"].values():
            assert schema.get("type") != "object"


async def test_a_tool_call_answers_with_the_record_the_tool_built():
    server = build(FakeApi({"/api/series": [fat_series(1)]}))
    result = await server.call_tool("list_series", {})
    assert result.structured_content["series"][0]["title"] == "Series 1"


async def test_an_api_refusal_comes_back_as_data_not_as_an_exception():
    class Refusing(FakeApi):
        async def get(self, path, params=None):
            raise ApiError(404, "series not found")

    server = build(Refusing({}))
    result = await server.call_tool("list_series", {})
    assert result.structured_content == {
        "ok": False,
        "error": "api_error",
        "message": "series not found",
        "status": 404,
    }


async def test_the_whole_review_and_download_loop_runs_without_the_web_interface():
    """The acceptance criterion, including a series whose candidates start empty."""
    api = LoopApi()
    server = build(api)

    queue = await server.call_tool("review_queue", {})
    series_id = queue.structured_content["pending"][0]["id"]

    empty = await server.call_tool("review_queue", {"series_id": series_id})
    assert empty.structured_content["candidates"] == []

    searched = await server.call_tool(
        "review_queue", {"series_id": series_id, "refresh": True}
    )
    assert searched.structured_content["search_job_id"] == 55

    api.finish_search()
    found = await server.call_tool("review_queue", {"series_id": series_id})
    url = found.structured_content["candidates"][0]["source_url"]

    confirmed = await server.call_tool(
        "confirm_mapping", {"series_id": series_id, "source_url": url}
    )
    assert confirmed.structured_content["ok"] is True

    queued = await server.call_tool(
        "download_chapters", {"series_id": series_id, "from_chapter": 1}
    )
    assert queued.structured_content["queued"] == 20


async def test_no_tool_can_answer_past_the_budget():
    api = LoopApi()
    server = build(api)
    for name, arguments in (
        ("list_series", {}),
        ("review_queue", {}),
        ("review_queue", {"series_id": 7}),
        ("jobs_status", {}),
        ("confirm_mapping", {"series_id": 7, "source_url": "https://mangadex.org/title/a"}),
        ("download_chapters", {"series_id": 7, "from_chapter": 1}),
        ("set_follow", {"series_id": 7, "enabled": True}),
        ("sync_lists", {"provider": "anilist"}),
    ):
        result = await server.call_tool(name, arguments)
        assert len(json.dumps(result.structured_content)) <= tools.RESPONSE_BUDGET, name


class LoopApi(FakeApi):
    """A library where one series is waiting and its candidates arrive late."""

    def __init__(self) -> None:
        super().__init__({})
        self.searched = False

    def finish_search(self) -> None:
        self.searched = True

    async def get(self, path, params=None):
        self.calls.append(("GET", path, params))
        if path == "/api/series":
            return [fat_series(n) for n in range(300)]
        if path == "/api/series/review/queue":
            return {
                "total": 1,
                "items": [{"id": 7, "title": "Berserk", "cover_url": None, "candidate_count": 0}],
            }
        if path == "/api/series/7/candidates":
            return {
                "series": {"id": 7, "title": "Berserk"},
                "candidates": _candidates()["candidates"] if self.searched else [],
            }
        if path == "/api/dashboard":
            return _dashboard()
        if path == "/api/jobs":
            return [_failed_job(n) for n in range(5)]
        if path == "/api/settings":
            return {"providers": {"mal": {}, "anilist": {}, "mangabaka": {}}}
        raise AssertionError(f"unexpected GET {path}")

    async def post(self, path, json=None):
        self.calls.append(("POST", path, json))
        if path.endswith("/search"):
            return {"ok": True, "job_id": 55}
        if path.endswith("/mapping"):
            return {"ok": True, "job_id": 56}
        if path.endswith("/download"):
            return {"ok": True, "queued": 20}
        if path.endswith("/auto-download"):
            return {"ok": True, "auto_download": True, "queued": 300}
        if path.startswith("/api/sync/"):
            return {"ok": True, "job_id": 57}
        raise AssertionError(f"unexpected POST {path}")
