"""API startup: the registry loads once, at boot, not per request or lazily."""

import pytest

from app.api import main

pytestmark = pytest.mark.asyncio


async def test_lifespan_loads_the_source_registry(monkeypatch):
    calls = []

    async def fake_reload(session):
        calls.append(session)

    monkeypatch.setattr(main, "reload_sources", fake_reload)

    async with main.lifespan(main.app):
        pass

    assert len(calls) == 1
