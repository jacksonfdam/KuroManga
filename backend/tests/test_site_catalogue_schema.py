"""site_catalogue and source_pref, asserted against a real database.

The two tables are deliberately unlinked: no foreign key runs from source_pref
back to site_catalogue, because a catalogue regeneration replaces
site_catalogue wholesale and a preference must survive that even when its key
is no longer among the new rows. A constraint that does not exist only fails
the day someone adds one by habit, so the absence is the test too.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import get_sessionmaker

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate site_catalogue, source_pref"))
        await session.commit()
    yield


async def _insert_catalogue_row(session, key: str = "mangadex") -> None:
    await session.execute(
        text(
            """
            insert into site_catalogue
                (key, name, template, base_url, lang, nsfw, overrides, rate_limit,
                 version, hand_ported)
            values
                (:key, 'MangaDex', 'mangadex', 'https://mangadex.org', 'en', false,
                 '{}'::jsonb, cast(:rate_limit as jsonb), '1.0.0', true)
            """
        ),
        {"key": key, "rate_limit": None},
    )


async def test_site_catalogue_key_is_unique():
    async with get_sessionmaker()() as session:
        await _insert_catalogue_row(session)
        await session.commit()
        with pytest.raises(IntegrityError):
            await _insert_catalogue_row(session)
            await session.commit()


async def test_site_catalogue_defaults():
    async with get_sessionmaker()() as session:
        await _insert_catalogue_row(session)
        await session.commit()
        row = (
            await session.execute(
                text("select nsfw, hand_ported, overrides from site_catalogue where key = 'mangadex'")
            )
        ).one()
    assert row.nsfw is False
    assert row.hand_ported is True
    assert row.overrides == {}


async def test_source_pref_defaults():
    async with get_sessionmaker()() as session:
        await session.execute(text("insert into source_pref (key) values ('mangadex')"))
        await session.commit()
        row = (
            await session.execute(
                text("select enabled, priority, rate_limit_override, disabled_reason"
                     " from source_pref where key = 'mangadex'")
            )
        ).one()
    assert row.enabled is True
    assert row.rate_limit_override is None
    assert row.disabled_reason is None


async def test_source_pref_has_no_foreign_key_to_the_catalogue():
    """A preference for a site the catalogue has never heard of must still insert.

    That is what lets a regeneration drop a row from site_catalogue without an
    on-delete rule reaching over and deleting the matching preference with it.
    """
    async with get_sessionmaker()() as session:
        await session.execute(
            text("insert into source_pref (key, enabled) values ('vanished-site', false)")
        )
        await session.commit()
        row = (
            await session.execute(
                text("select enabled from source_pref where key = 'vanished-site'")
            )
        ).one()
    assert row.enabled is False
