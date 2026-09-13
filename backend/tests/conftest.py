import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5433")

FIXTURES = Path(__file__).parent / "fixtures"


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
