"""Reading the generated catalogue into the database.

The generator writes a file; this is what puts it in `site_catalogue`. The
rules it has to keep are the ones that make the two tables separate in the
first place: running it twice changes nothing, and a preference the user set
survives it.
"""

import json

import pytest
from sqlalchemy import text

from app.catalogue.loader import DEFAULT_CATALOGUE_PATH, entries_from_file, load_catalogue
from app.db import get_sessionmaker

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate site_catalogue, source_pref"))
        await session.commit()
    yield


async def _count(table: str) -> int:
    async with get_sessionmaker()() as session:
        return int((await session.execute(text(f"select count(*) from {table}"))).scalar_one())


def test_the_shipped_catalogue_parses_into_entries():
    entries = entries_from_file(DEFAULT_CATALOGUE_PATH)

    # The file the generator commits is the one this ships with; if it stops
    # parsing, that is a break between the two and not a test fixture problem.
    assert len(entries) > 100
    assert all(e.key and e.template and e.base_url for e in entries)


async def test_loading_puts_the_generated_rows_in_the_database():
    written = await load_catalogue()

    assert written > 100
    assert await _count("site_catalogue") == written


async def test_loading_twice_changes_nothing_the_second_time():
    first = await load_catalogue()
    second = await load_catalogue()

    assert first == second
    assert await _count("site_catalogue") == first


async def test_a_preference_the_user_set_survives_a_reload():
    await load_catalogue()
    async with get_sessionmaker()() as session:
        key = (
            await session.execute(text("select key from site_catalogue order by key limit 1"))
        ).scalar_one()
        await session.execute(
            text("insert into source_pref (key, enabled) values (:k, false)"), {"k": key}
        )
        await session.commit()

    await load_catalogue()

    async with get_sessionmaker()() as session:
        still = (
            await session.execute(
                text("select enabled from source_pref where key = :k"), {"k": key}
            )
        ).scalar_one()
    # Keeping the two tables apart is only worth anything if this holds: a site
    # turned off stays off when the catalogue is regenerated under it.
    assert still is False


async def test_a_loaded_row_is_not_searched_until_it_is_enabled():
    await load_catalogue()

    # source_pref is untouched by loading, and the registry joins against it,
    # so arriving in the catalogue is not the same as being switched on.
    assert await _count("source_pref") == 0


def test_a_file_that_is_not_a_list_of_entries_is_refused(tmp_path):
    bad = tmp_path / "catalogue.json"
    bad.write_text(json.dumps({"not": "a list"}))

    with pytest.raises(ValueError, match="list"):
        entries_from_file(bad)


def test_a_row_missing_a_field_names_the_row_rather_than_the_field(tmp_path):
    bad = tmp_path / "catalogue.json"
    bad.write_text(json.dumps([{"key": "a.site", "name": "A Site"}]))

    # A generated file with 491 rows is not something to read by eye, so the
    # error has to say which row to look at.
    with pytest.raises(ValueError, match="a.site"):
        entries_from_file(bad)
