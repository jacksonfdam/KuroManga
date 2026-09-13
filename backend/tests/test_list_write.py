"""Writing the chosen status outward, one independent target at a time."""

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.handlers.list_write import pending_targets, record_result, targets_for

pytestmark = pytest.mark.asyncio


class Row:
    def __init__(self, provider="anilist", media_id="3000", alt_ids=None, meta=None):
        self.provider = provider
        self.provider_media_id = media_id
        self.alt_ids = alt_ids or {}
        self.meta = meta or {}


def test_a_suggestion_known_to_both_providers_writes_to_both():
    row = Row(alt_ids={"mal": "500"}, meta={"mangadex_uuid": "uuid-1"})
    assert targets_for(row) == [("anilist", "3000"), ("mal", "500"), ("mangadex", "uuid-1")]


def test_a_suggestion_without_a_mangadex_match_simply_has_no_such_target():
    assert targets_for(Row()) == [("anilist", "3000")]


def test_a_retry_only_repeats_the_targets_that_failed():
    row = Row(
        alt_ids={"mal": "500"},
        meta={
            "mangadex_uuid": "uuid-1",
            "write_results": [
                {"target": "anilist", "ok": True},
                {"target": "mal", "ok": False, "error": "500 from mal"},
            ],
        },
    )
    assert pending_targets(row) == [("mal", "500"), ("mangadex", "uuid-1")]


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate suggestion restart identity cascade"))
        await session.commit()
    yield


async def test_results_accumulate_on_the_suggestion():
    async with get_sessionmaker()() as session:
        suggestion_id = (
            await session.execute(
                text(
                    """
                    insert into suggestion (provider, provider_media_id, title, alt_ids, meta)
                    values ('anilist', '3000', 'V', '{}'::jsonb, '{}'::jsonb) returning id
                    """
                )
            )
        ).scalar_one()
        await record_result(session, suggestion_id, "anilist", ok=True, error=None)
        await record_result(session, suggestion_id, "mal", ok=False, error="boom")
        await session.commit()
        meta = (
            await session.execute(
                text("select meta from suggestion where id = :id"), {"id": suggestion_id}
            )
        ).scalar_one()
    results = {r["target"]: r for r in meta["write_results"]}
    assert results["anilist"]["ok"] is True
    assert results["mal"]["error"] == "boom"
