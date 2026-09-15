"""Worker startup: the registry loads once, at boot, not queried per job."""

import pytest

from app.worker import main as worker_main

pytestmark = pytest.mark.asyncio


async def test_load_registry_calls_reload(monkeypatch):
    calls = []

    async def fake_reload(session):
        calls.append(session)

    monkeypatch.setattr(worker_main, "reload_sources", fake_reload)

    await worker_main.load_registry()

    assert len(calls) == 1
