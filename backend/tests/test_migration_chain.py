from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory


@pytest.fixture(scope="session", autouse=True)
def schema():
    """Shadow conftest's autouse migration fixture: it runs `alembic upgrade head`,
    which is exactly the command that exits 255 on a fork, so it would fail this
    module's session setup before the test below ever got to explain why.
    """
    return


def test_migration_chain_has_a_single_head() -> None:
    """Two migrations written from the same parent on separate branches fork the chain.

    `alembic upgrade head` then refuses to pick one and exits 255, which fails the
    session-scoped migration fixture and every test in the suite — on any branch,
    even one that touches no Python at all (#71). Reading the chain here needs no
    database, so a developer who just wrote a migration learns about a fork before
    pushing rather than from a red pipeline once someone else's branch lands too.
    """
    ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    config = Config(str(ini_path))
    script = ScriptDirectory.from_config(config)

    heads = script.get_heads()

    assert len(heads) == 1, (
        f"the migration chain has {len(heads)} heads, not one: {sorted(heads)}. "
        "Two migrations were written from the same parent on separate branches. "
        "Re-parent one onto the other by changing its down_revision to the other "
        "head's revision id, and leave its own revision id alone — that id is what "
        "a database that already ran the migration has recorded in alembic_version, "
        "so renaming it strands that database rather than fixing anything. "
        "See d4fa919 for a worked example."
    )
