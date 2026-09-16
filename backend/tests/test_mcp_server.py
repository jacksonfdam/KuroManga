"""The tools as the client sees them.

Registration is worth a test of its own: a tool whose schema drifts from the
function behind it fails at call time, in a client, with no traceback here.
"""

import pytest

from app.mcp.api import ApiError
from app.mcp.server import build
from tests.test_mcp_tools_read import FakeApi, fat_series

pytestmark = pytest.mark.asyncio


async def test_the_whole_loop_is_reachable_and_nothing_else_is():
    listed = await build(FakeApi({})).list_tools()
    assert {tool.name for tool in listed} == {
        "list_series",
        "review_queue",
        "jobs_status",
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
