"""Token storage and renewal.

MyAnimeList access tokens last an hour, so a six-hourly sync that never refreshes
would fail on every run but the first. These cover that path.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import Provider
from app.providers import tokens as token_store
from app.providers.base import TokenSet

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def clean_tokens():
    async with get_sessionmaker()() as session:
        await session.execute(text("delete from provider_token"))
        await session.commit()
    yield


def test_a_token_without_an_expiry_never_looks_expiring():
    assert token_store.is_expiring(None) is False


def test_a_token_already_past_its_expiry_is_expiring():
    assert token_store.is_expiring(datetime.now(UTC) - timedelta(minutes=1)) is True


def test_a_token_inside_the_margin_is_refreshed_early():
    assert token_store.is_expiring(datetime.now(UTC) + timedelta(minutes=2)) is True


def test_a_token_with_time_left_is_left_alone():
    assert token_store.is_expiring(datetime.now(UTC) + timedelta(hours=2)) is False


async def test_an_unconnected_provider_is_reported_as_such():
    async with get_sessionmaker()() as session:
        with pytest.raises(token_store.NotConnected):
            await token_store.access_token_for(session, Provider.MAL)


async def test_a_live_token_is_returned_untouched():
    async with get_sessionmaker()() as session:
        await token_store.store_token(
            session, Provider.MAL, access_token="live", refresh_token="r", expires_in=3600
        )
        await session.commit()
        assert await token_store.access_token_for(session, Provider.MAL) == "live"


async def test_an_expiring_token_is_renewed_and_persisted(monkeypatch):
    class Stub:
        async def refresh(self, refresh_token: str):
            assert refresh_token == "old-refresh"
            return TokenSet(access_token="fresh", refresh_token="new-refresh", expires_in=3600)

    monkeypatch.setattr(token_store, "get_source", lambda provider: Stub())

    async with get_sessionmaker()() as session:
        await token_store.store_token(
            session, Provider.MAL, access_token="stale", refresh_token="old-refresh", expires_in=60
        )
        await session.commit()

        assert await token_store.access_token_for(session, Provider.MAL) == "fresh"
        await session.commit()

        result = await session.execute(
            text("select access_token, refresh_token from provider_token where provider = 'mal'")
        )
        row = result.first()
    assert row.access_token == "fresh"
    assert row.refresh_token == "new-refresh"


async def test_a_provider_that_cannot_refresh_keeps_using_its_token(monkeypatch):
    class Stub:
        async def refresh(self, refresh_token: str):
            return None

    monkeypatch.setattr(token_store, "get_source", lambda provider: Stub())

    async with get_sessionmaker()() as session:
        await token_store.store_token(
            session, Provider.ANILIST, access_token="long-lived", refresh_token="r", expires_in=10
        )
        await session.commit()
        assert await token_store.access_token_for(session, Provider.ANILIST) == "long-lived"


async def test_storing_again_without_a_refresh_token_keeps_the_stored_one():
    async with get_sessionmaker()() as session:
        await token_store.store_token(
            session, Provider.MAL, access_token="a", refresh_token="keep-me", expires_in=3600
        )
        await token_store.store_token(
            session, Provider.MAL, access_token="b", refresh_token=None, expires_in=3600
        )
        await session.commit()
        result = await session.execute(
            text("select access_token, refresh_token from provider_token where provider = 'mal'")
        )
        row = result.first()
    assert row.access_token == "b"
    assert row.refresh_token == "keep-me"
