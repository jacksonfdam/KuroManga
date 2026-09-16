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


async def test_a_site_the_user_enabled_is_not_deleted_by_a_regeneration():
    """The regression that took three working sources off a running install.

    Migration 0013 seeded thunderscans, vortexscans and orionscans by hand with
    real template names. The generated catalogue does not contain those keys, so
    the first load deleted all three and left their preferences orphaned - the
    pipeline went from seven sources to four with nothing said about it.

    A regeneration may retire a site upstream dropped. It may not switch off one
    the user is using.
    """
    async with get_sessionmaker()() as session:
        await replace_catalogue(session, [_entry("hand.seeded"), _entry("generated.one")])
        await session.execute(
            text("insert into source_pref (key, enabled) values ('hand.seeded', true)")
        )
        await session.commit()

        # A regeneration that knows nothing about the hand-seeded key.
        await replace_catalogue(session, [_entry("generated.one")])
        await session.commit()

        surviving = set(
            (await session.execute(text("select key from site_catalogue"))).scalars()
        )

    assert surviving == {"hand.seeded", "generated.one"}


async def test_a_site_whose_preference_is_disabled_is_still_retired():
    async with get_sessionmaker()() as session:
        await replace_catalogue(session, [_entry("switched.off"), _entry("still.there")])
        await session.execute(
            text("insert into source_pref (key, enabled) values ('switched.off', false)")
        )
        await session.commit()

        await replace_catalogue(session, [_entry("still.there")])
        await session.commit()

        surviving = set(
            (await session.execute(text("select key from site_catalogue"))).scalars()
        )

    # A disabled preference is not somebody using the site. Sparing those would
    # mean a catalogue that never shrinks.
    assert surviving == {"still.there"}


async def test_a_site_nobody_has_an_opinion_about_is_still_retired():
    async with get_sessionmaker()() as session:
        await replace_catalogue(session, [_entry("gone.upstream"), _entry("still.there")])
        await session.commit()

        await replace_catalogue(session, [_entry("still.there")])
        await session.commit()

        surviving = set(
            (await session.execute(text("select key from site_catalogue"))).scalars()
        )

    # Without a preference there is nothing to protect, and a catalogue that
    # kept every site it ever saw would never shrink.
    assert surviving == {"still.there"}


async def _enable(session, key: str) -> None:
    await session.execute(
        text("insert into source_pref (key, enabled) values (:key, true)"), {"key": key}
    )


async def test_a_generated_duplicate_of_a_running_site_is_not_written():
    """Migration 0013 seeded three sites by hand before a generator existed.

    The generator then produced its own rows for the same sites under
    `<lang>.<name>`, and the database carried each twice — the seeded one
    working, the generated one inert beside it in Settings.
    """
    async with get_sessionmaker()() as session:
        await replace_catalogue(session, [_entry("thunderscans", base_url="https://en-thunderscans.com")])
        await _enable(session, "thunderscans")
        await session.commit()

        await replace_catalogue(
            session,
            [
                _entry("en.thunderscans", base_url="https://en-thunderscans.com"),
                _entry("en.other", base_url="https://other.example"),
            ],
        )
        await session.commit()

        keys = (
            (await session.execute(text("select key from site_catalogue order by key")))
            .scalars()
            .all()
        )

    assert keys == ["en.other", "thunderscans"]


async def test_the_running_site_keeps_its_preference():
    """Renaming instead would move the preference onto a row that may behave
    differently — `en.thunderscans` is hand_ported false upstream, so the site
    would have arrived inert."""
    async with get_sessionmaker()() as session:
        await replace_catalogue(session, [_entry("thunderscans", base_url="https://en-thunderscans.com")])
        await _enable(session, "thunderscans")
        await session.commit()

        await replace_catalogue(
            session,
            [_entry("en.thunderscans", base_url="https://en-thunderscans.com", hand_ported=False)],
        )
        await session.commit()

        row = (
            await session.execute(
                text(
                    "select c.key, c.hand_ported, p.enabled from site_catalogue c"
                    " join source_pref p using (key)"
                )
            )
        ).mappings().one()

    assert row["key"] == "thunderscans"
    assert row["hand_ported"] is True
    assert row["enabled"] is True


async def test_a_disabled_duplicate_does_not_block_the_generated_row():
    """Only a site somebody is actually using wins. A disabled seeded row is
    not somebody using the site, and sparing those would keep every retired
    key forever."""
    async with get_sessionmaker()() as session:
        await replace_catalogue(session, [_entry("oldkey", base_url="https://same.example")])
        await session.execute(
            text("insert into source_pref (key, enabled) values ('oldkey', false)")
        )
        await session.commit()

        await replace_catalogue(session, [_entry("en.newkey", base_url="https://same.example")])
        await session.commit()

        keys = (
            (await session.execute(text("select key from site_catalogue"))).scalars().all()
        )

    assert keys == ["en.newkey"]


async def test_the_host_comparison_ignores_scheme_and_www():
    async with get_sessionmaker()() as session:
        await replace_catalogue(session, [_entry("seeded", base_url="https://www.site.example/")])
        await _enable(session, "seeded")
        await session.commit()

        await replace_catalogue(session, [_entry("en.site", base_url="http://site.example")])
        await session.commit()

        keys = (
            (await session.execute(text("select key from site_catalogue"))).scalars().all()
        )

    assert keys == ["seeded"]
