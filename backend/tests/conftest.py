import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5433")

FIXTURES = Path(__file__).parent / "fixtures"

# Mirrors migration 0012's seed: test_catalogue_repo.py truncates site_catalogue
# and source_pref for its own tests, and one of them upserts over key
# "mangadex" with a fake, non-native template as part of proving the delete
# scoping - so a plain ON CONFLICT DO NOTHING would leave that row wrong for
# every test that runs afterward. DO UPDATE forces it back to native shape
# regardless of what an earlier test left behind.
_NATIVE_CATALOGUE_SEED = text(
    """
    insert into site_catalogue
        (key, name, template, base_url, lang, nsfw, overrides, rate_limit, version, hand_ported)
    values
        ('mangadex', 'MangaDex', 'native', 'https://mangadex.org', 'en', false, '{}'::jsonb,
         null, '1.0.0', true),
        ('weebcentral', 'WeebCentral', 'native', 'https://weebcentral.com', 'en', false,
         '{}'::jsonb, null, '1.0.0', true)
    on conflict (key) do update
       set template = excluded.template,
           base_url = excluded.base_url,
           name = excluded.name
    """
)
_NATIVE_SOURCE_PREF_SEED = text(
    """
    insert into source_pref (key, enabled) values ('mangadex', true), ('weebcentral', true)
    on conflict (key) do update set enabled = excluded.enabled
    """
)


@pytest.fixture(scope="session", autouse=True)
def schema():
    """Migrate the test database once, for every module that touches it.

    This lives here rather than in the modules that happen to need it because a
    module that truncates a table without owning this fixture passes on any
    database that has been migrated before and fails on a fresh one. That is
    invisible locally and fails every time in continuous integration.
    """
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], check=True, capture_output=True
    )


@pytest.fixture(autouse=True)
async def source_registry(schema):
    """Boot-equivalent for the test session: the registry is loaded, not queried.

    Production loads it once, at process startup. A test run has no such
    single moment - test_catalogue_repo.py in particular truncates the tables
    the registry is built from - so this reseeds and reloads before every
    test instead, which keeps `source_for_url` and `get_source` working for
    any test that never thinks about the registry at all.
    """
    from app.db import get_sessionmaker
    from app.sources import reload as reload_sources

    async with get_sessionmaker()() as session:
        await session.execute(_NATIVE_CATALOGUE_SEED)
        await session.execute(_NATIVE_SOURCE_PREF_SEED)
        await session.commit()
        await reload_sources(session)


@pytest.fixture(autouse=True)
async def reset_engine():
    """asyncpg connections belong to the loop that opened them.

    pytest-asyncio gives each test its own loop, so the cached engine has to go
    with it or the next test inherits connections attached to a dead loop.
    """
    yield
    import app.db as db

    if db._engine is not None:
        await db._engine.dispose()
        db._engine = None
        db._sessionmaker = None


@pytest.fixture
def fixture():
    def load(name: str) -> dict:
        return json.loads((FIXTURES / name).read_text())

    return load
