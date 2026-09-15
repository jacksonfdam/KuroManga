"""app.sources.registry: builds the runtime registry from site_catalogue and source_pref.

Uses the real seeded rows (migration 0012) rather than a fixture catalogue,
because proving the registry actually reflects the database - not a stand-in
for it - is the point of this task.
"""

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.sources import all_sources, get_source, reload, source_for_url

pytestmark = pytest.mark.asyncio

# conftest.py's source_registry fixture reseeds and reloads before every test,
# so each test here starts from a known-good registry and only has to clean
# up the extra rows it adds itself.


async def test_reload_populates_the_registry_from_the_seeded_native_rows():
    async with get_sessionmaker()() as session:
        await reload(session)
    sites = {source.site for source in all_sources()}
    assert {"mangadex", "weebcentral"} <= sites


async def test_a_source_disabled_in_preferences_is_absent_from_all_sources():
    async with get_sessionmaker()() as session:
        await session.execute(text("update source_pref set enabled = false where key = 'mangadex'"))
        await session.commit()
        try:
            await reload(session)
            assert "mangadex" not in {source.site for source in all_sources()}
            with pytest.raises(ValueError):
                get_source("mangadex")
        finally:
            await session.execute(
                text("update source_pref set enabled = true where key = 'mangadex'")
            )
            await session.commit()
            await reload(session)


async def test_a_non_native_template_row_is_skipped():
    async with get_sessionmaker()() as session:
        await reload(session)
        baseline = {source.site for source in all_sources()}

        await session.execute(
            text(
                "insert into site_catalogue"
                " (key, name, template, base_url, lang, nsfw, overrides, version, hand_ported)"
                " values ('fakemadara', 'Fake', 'madara', 'https://fake.example', 'en',"
                " false, '{}'::jsonb, '1.0.0', true)"
            )
        )
        await session.execute(
            text("insert into source_pref (key, enabled) values ('fakemadara', true)")
        )
        await session.commit()
        try:
            await reload(session)
            assert {source.site for source in all_sources()} == baseline
            assert get_source("mangadex").site == "mangadex"
        finally:
            await session.execute(text("delete from source_pref where key = 'fakemadara'"))
            await session.execute(text("delete from site_catalogue where key = 'fakemadara'"))
            await session.commit()
            await reload(session)


async def test_a_native_row_with_no_class_registered_for_its_key_is_skipped():
    async with get_sessionmaker()() as session:
        await reload(session)
        baseline = {source.site for source in all_sources()}

        await session.execute(
            text(
                "insert into site_catalogue"
                " (key, name, template, base_url, lang, nsfw, overrides, version, hand_ported)"
                " values ('unknownnative', 'Unknown', 'native', 'https://unknown.example', 'en',"
                " false, '{}'::jsonb, '1.0.0', true)"
            )
        )
        await session.execute(
            text("insert into source_pref (key, enabled) values ('unknownnative', true)")
        )
        await session.commit()
        try:
            await reload(session)
            assert {source.site for source in all_sources()} == baseline
        finally:
            await session.execute(text("delete from source_pref where key = 'unknownnative'"))
            await session.execute(text("delete from site_catalogue where key = 'unknownnative'"))
            await session.commit()
            await reload(session)


async def test_source_for_url_names_the_enabled_sites_when_nothing_matches():
    async with get_sessionmaker()() as session:
        await reload(session)
    with pytest.raises(ValueError, match="mangadex"):
        source_for_url("https://totally-unknown-site.example/x")


async def test_the_migration_seeded_both_native_sources_enabled():
    async with get_sessionmaker()() as session:
        rows = (
            (
                await session.execute(
                    text(
                        "select c.key, c.template, p.enabled"
                        " from site_catalogue c join source_pref p using (key)"
                        " where c.key in ('mangadex', 'comick') order by c.key"
                    )
                )
            )
            .mappings()
            .all()
        )
    assert [dict(row) for row in rows] == [
        {"key": "comick", "template": "native", "enabled": True},
        {"key": "mangadex", "template": "native", "enabled": True},
    ]
