"""app.mcp.api, the server's one dependency.

Every test drives a MockTransport rather than a live API: the point is the
request this client sends and the refusal it raises, not FastAPI's routing.
"""

import httpx
import pytest

from app.mcp.api import ApiError, KuroMangaApi

pytestmark = pytest.mark.asyncio


def _api(handler):
    transport = httpx.MockTransport(handler)
    return KuroMangaApi("http://api.test", client=httpx.AsyncClient(transport=transport))


async def test_a_get_is_addressed_at_the_configured_base_url():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json=[])

    await _api(handler).get("/api/series")
    assert seen["url"] == "http://api.test/api/series"


async def test_an_unset_query_parameter_is_not_sent_as_an_empty_one():
    seen = {}

    def handler(request):
        seen["query"] = request.url.query.decode()
        return httpx.Response(200, json=[])

    await _api(handler).get("/api/jobs", {"state": None, "limit": 5})
    assert seen["query"] == "limit=5"


async def test_a_refusal_carries_the_status_and_the_reason():
    def handler(request):
        return httpx.Response(400, json={"detail": "no source handles that url"})

    with pytest.raises(ApiError) as raised:
        await _api(handler).post("/api/series/1/mapping", {"source_url": "nonsense"})
    assert raised.value.status == 400
    assert raised.value.detail == "no source handles that url"


async def test_a_refusal_with_no_json_body_reports_what_was_sent():
    def handler(request):
        return httpx.Response(502, text="bad gateway")

    with pytest.raises(ApiError) as raised:
        await _api(handler).get("/api/series")
    assert raised.value.detail == "bad gateway"


async def test_the_base_url_keeps_no_trailing_slash():
    assert KuroMangaApi("http://api.test/").base_url == "http://api.test"
