"""MangaDex personal client tokens.

Access tokens live fifteen minutes, so renewal is the behaviour worth covering:
a cached token is reused, an expired one is refreshed, and a refresh that is
rejected falls back to signing in again.
"""

import httpx
import pytest

from app.config import get_settings
from app.sources.mangadex_auth import (
    TokenCache,
    password_grant_form,
    refresh_grant_form,
)

pytestmark = pytest.mark.asyncio

CREDENTIALS = {
    "MANGADEX_CLIENT_ID": "personal-client-1",
    "MANGADEX_CLIENT_SECRET": "shh",
    "MANGADEX_USERNAME": "reader",
    "MANGADEX_PASSWORD": "hunter2",
}


@pytest.fixture
def configured(monkeypatch):
    for key, value in CREDENTIALS.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_the_password_grant_sends_the_documented_fields():
    form = password_grant_form("id", "secret", "reader", "pw")
    assert form == {
        "grant_type": "password",
        "username": "reader",
        "password": "pw",
        "client_id": "id",
        "client_secret": "secret",
    }


def test_the_refresh_grant_sends_the_documented_fields():
    form = refresh_grant_form("id", "secret", "refresh-1")
    assert form == {
        "grant_type": "refresh_token",
        "refresh_token": "refresh-1",
        "client_id": "id",
        "client_secret": "secret",
    }


async def test_no_credentials_means_no_token(monkeypatch):
    for key in CREDENTIALS:
        monkeypatch.setenv(key, "")
    get_settings.cache_clear()
    assert await TokenCache().token() is None
    get_settings.cache_clear()


async def test_a_first_call_signs_in_with_the_password_grant(configured):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200, json={"access_token": "tok-1", "expires_in": 900})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        cache = TokenCache()
        assert await cache.token(client) == "tok-1"
    assert seen[0]["grant_type"] == "password"
    assert seen[0]["username"] == "reader"


async def test_a_cached_token_is_reused_without_another_request(configured):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"access_token": "tok-1", "expires_in": 900})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        cache = TokenCache()
        await cache.token(client)
        await cache.token(client)
    assert calls == 1


async def test_an_expired_token_is_refreshed_with_the_refresh_grant(configured):
    grants: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        form = dict(httpx.QueryParams(request.content.decode()))
        grants.append(form["grant_type"])
        return httpx.Response(
            200,
            json={"access_token": f"tok-{len(grants)}", "refresh_token": "r-1", "expires_in": 900},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        cache = TokenCache()
        await cache.token(client)
        cache._expires_at = 0  # pretend the fifteen minutes elapsed
        assert await cache.token(client) == "tok-2"
    assert grants == ["password", "refresh_token"]


async def test_a_rejected_refresh_falls_back_to_signing_in(configured):
    grants: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        form = dict(httpx.QueryParams(request.content.decode()))
        grants.append(form["grant_type"])
        if form["grant_type"] == "refresh_token":
            return httpx.Response(400, json={"error": "invalid_grant"})
        return httpx.Response(
            200,
            json={"access_token": "fresh", "refresh_token": "r-2", "expires_in": 900},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        cache = TokenCache()
        await cache.token(client)
        cache._expires_at = 0
        assert await cache.token(client) == "fresh"
    assert grants == ["password", "refresh_token", "password"]
