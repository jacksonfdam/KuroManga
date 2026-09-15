"""replace_catalogue: the upsert-by-key regeneration relies on.

A regeneration hands this function the whole new catalogue and expects the
old one gone except for what the new run repeated - source_pref is never in
its argument list and must not move because of anything done here.
"""

import pytest
from sqlalchemy import text

from app.catalogue.repo import CatalogueEntry, replace_catalogue
from app.db import get_sessionmaker

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate site_catalogue, source_pref"))
        await session.commit()
    yield


def _entry(key: str, **overrides) -> CatalogueEntry:
    fields = {
        "key": key,
        "name": key.title(),
        "template": "madara",
        "base_url": f"https://{key}.example",
        "lang": "en",
        "nsfw": False,
        "overrides": {},
        "rate_limit": None,
        "version": "1.0.0",
        "hand_ported": True,
    }
    fields.update(overrides)
    return CatalogueEntry(**fields)


async def test_replace_catalogue_inserts_new_rows():
    async with get_sessionmaker()() as session:
        await replace_catalogue(session, [_entry("mangadex"), _entry("comick")])
        await session.commit()
        keys = (
            (await session.execute(text("select key from site_catalogue order by key")))
            .scalars()
            .all()
        )
    assert keys == ["comick", "mangadex"]


async def test_replace_catalogue_updates_an_existing_row_in_place():
    async with get_sessionmaker()() as session:
        await replace_catalogue(session, [_entry("mangadex", version="1.0.0")])
        await session.commit()
        await replace_catalogue(session, [_entry("mangadex", version="1.0.1", nsfw=True)])
        await session.commit()
        row = (
            await session.execute(
                text("select version, nsfw from site_catalogue where key = 'mangadex'")
            )
        ).one()
    assert row.version == "1.0.1"
    assert row.nsfw is True


async def test_replace_catalogue_drops_a_site_the_new_run_did_not_produce():
    async with get_sessionmaker()() as session:
        await replace_catalogue(session, [_entry("mangadex"), _entry("comick")])
        await session.commit()
        await replace_catalogue(session, [_entry("mangadex")])
        await session.commit()
        keys = (await session.execute(text("select key from site_catalogue"))).scalars().all()
    assert keys == ["mangadex"]


async def test_a_native_row_survives_a_regeneration_that_does_not_mention_it():
    """mangadex and comick are hand-written, not generated.

    The generator parses the Tachiyomi extension repository, which does not
    contain either of them, so every regeneration leaves them out of its own
    output. The delete this function issues must not read that as "gone".
    """
    async with get_sessionmaker()() as session:
        await replace_catalogue(session, [_entry("mangadex", template="native")])
        await session.commit()

        await replace_catalogue(session, [_entry("comick")])
        await session.commit()

        keys = (
            (await session.execute(text("select key from site_catalogue order by key")))
            .scalars()
            .all()
        )
    assert keys == ["comick", "mangadex"]


async def test_a_preference_survives_its_site_leaving_the_catalogue():
    """The whole point of keeping the tables apart, proved end to end.

    A regeneration that no longer produces "comick" must not touch the
    preference recorded for it - not delete it, not flip enabled, nothing.
    """
    async with get_sessionmaker()() as session:
        await replace_catalogue(session, [_entry("mangadex"), _entry("comick")])
        await session.execute(
            text(
                "insert into source_pref (key, enabled, priority)"
                " values ('comick', false, 5), ('mangadex', true, 10)"
            )
        )
        await session.commit()

        # The regenerated catalogue no longer carries comick at all.
        await replace_catalogue(session, [_entry("mangadex")])
        await session.commit()

        prefs = (
            (
                await session.execute(
                    text("select key, enabled, priority from source_pref order by key")
                )
            )
            .mappings()
            .all()
        )
        catalogue_keys = (await session.execute(text("select key from site_catalogue"))).scalars().all()

    assert catalogue_keys == ["mangadex"]
    assert [dict(row) for row in prefs] == [
        {"key": "comick", "enabled": False, "priority": 5},
        {"key": "mangadex", "enabled": True, "priority": 10},
    ]


async def test_a_preference_survives_a_regeneration_that_still_carries_its_site():
    """Re-upserting a site's catalogue row must not touch anyone's preference for it."""
    async with get_sessionmaker()() as session:
        await replace_catalogue(session, [_entry("mangadex")])
        await session.execute(
            text("insert into source_pref (key, enabled) values ('mangadex', false)")
        )
        await session.commit()

        await replace_catalogue(session, [_entry("mangadex", version="2.0.0")])
        await session.commit()

        enabled = (
            await session.execute(text("select enabled from source_pref where key = 'mangadex'"))
        ).scalar_one()
    assert enabled is False


async def test_replace_catalogue_refuses_an_empty_catalogue():
    """A generator that parsed nothing must not disable every source at once.

    The registry is built from this table, so an accepted empty list would
    take searching and downloading down for the whole library, and the stored
    catalogue it overwrote is the one thing that still worked.
    """
    async with get_sessionmaker()() as session:
        await replace_catalogue(session, [_entry("mangadex")])
        await session.commit()

        with pytest.raises(ValueError):
            await replace_catalogue(session, [])
        await session.rollback()

        keys = (await session.execute(text("select key from site_catalogue"))).scalars().all()
    assert keys == ["mangadex"]
