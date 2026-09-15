"""The worker refuses to start when the library it can see contradicts the database.

A `docker compose up` from a git worktree resolves the relative default
`./data/manga` against that worktree — a directory that has never existed — and
Docker creates a missing bind source silently, as an empty one. The worker then
writes every archive into a phantom directory, marks each chapter downloaded,
shows none of it in Komga, and re-fetches the same chapters on every run.
"""

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.worker.main import LibraryUnreachable, verify_library_mount

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series, chapter restart identity cascade"))
        await session.commit()
    yield


async def _downloaded_chapter(path: str) -> None:
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta)"
                    " values ('Held', 'held', false, '{}'::jsonb) returning id"
                )
            )
        ).scalar_one()
        await session.execute(
            text(
                "insert into chapter (series_id, number, state, file_path)"
                " values (:id, 1, 'downloaded', :path)"
            ),
            {"id": series_id, "path": path},
        )
        await session.commit()


async def test_an_empty_library_with_downloaded_chapters_stops_the_worker(tmp_path, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "get_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr("app.worker.main.get_settings", lambda: _settings(tmp_path))
    await _downloaded_chapter(str(tmp_path / "held" / "held - Ch.0001.cbz"))

    with pytest.raises(LibraryUnreachable, match="marked downloaded"):
        await verify_library_mount()


async def test_a_fresh_install_starts_normally(tmp_path, monkeypatch):
    """Empty library, nothing downloaded: the ordinary first run, not a fault."""
    monkeypatch.setattr("app.worker.main.get_settings", lambda: _settings(tmp_path))

    await verify_library_mount()


async def test_a_library_holding_archives_starts_normally(tmp_path, monkeypatch):
    monkeypatch.setattr("app.worker.main.get_settings", lambda: _settings(tmp_path))
    await _downloaded_chapter(str(tmp_path / "held" / "held - Ch.0001.cbz"))
    series = tmp_path / "held"
    series.mkdir()
    (series / "held - Ch.0001.cbz").write_bytes(b"PK\x03\x04")

    await verify_library_mount()


async def test_a_missing_library_directory_is_the_same_fault(tmp_path, monkeypatch):
    """Docker creates a missing bind source as an empty directory, but a path that
    is simply absent must not crash on its way to the same conclusion."""
    monkeypatch.setattr("app.worker.main.get_settings", lambda: _settings(tmp_path / "nothing"))
    await _downloaded_chapter("/manga/held/held - Ch.0001.cbz")

    with pytest.raises(LibraryUnreachable):
        await verify_library_mount()


def _settings(library):
    class _Stub:
        library_path = library

    return _Stub()
