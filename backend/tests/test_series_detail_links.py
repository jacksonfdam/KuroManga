"""What the detail screen needs to link somewhere: Komga's ids, and which
similar works the reader already owns.

Every one of these is an absence test as much as a presence test. A link built
from a missing id lands on a Komga 404, and a similar work wrongly marked as
owned sends the reader to somebody else's series — both worse than the screen
offering nothing.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                "truncate job, job_event, series, list_entry, source_mapping, "
                "series_candidate, chapter restart identity cascade"
            )
        )
        await session.commit()
    yield


async def _series(session, title: str, *, komga_series_id: str | None = None) -> int:
    row = await session.execute(
        text(
            """
            insert into series (canonical_title, slug, komga_series_id, needs_review, meta)
            values (:title, :slug, :komga, false, '{}'::jsonb)
            returning id
            """
        ),
        {"title": title, "slug": title.lower().replace(" ", "-"), "komga": komga_series_id},
    )
    return row.scalar_one()


async def test_the_series_carries_komgas_own_id():
    async with get_sessionmaker()() as session:
        series_id = await _series(session, "Linked", komga_series_id="0RME2MM66H7EE")
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        body = (await http.get(f"/api/series/{series_id}")).json()

    assert body["series"]["komga_series_id"] == "0RME2MM66H7EE"


async def test_a_series_komga_has_never_seen_carries_none():
    """Null, not an empty string: the screen decides whether to offer the link."""
    async with get_sessionmaker()() as session:
        series_id = await _series(session, "Unscanned")
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        body = (await http.get(f"/api/series/{series_id}")).json()

    assert body["series"]["komga_series_id"] is None


async def test_only_a_chapter_komga_indexed_carries_a_book_id():
    async with get_sessionmaker()() as session:
        series_id = await _series(session, "Half Downloaded")
        await session.execute(
            text(
                """
                insert into chapter (series_id, number, state, komga_book_id)
                values (:id, 1, 'downloaded', '0RME38V6JH06T'),
                       (:id, 2, 'known', null)
                """
            ),
            {"id": series_id},
        )
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        body = (await http.get(f"/api/series/{series_id}")).json()

    by_number = {chapter["number"]: chapter for chapter in body["chapters"]}
    assert by_number[1.0]["komga_book_id"] == "0RME38V6JH06T"
    assert by_number[2.0]["komga_book_id"] is None


async def test_a_similar_work_already_in_the_library_carries_its_series_id():
    """Matched on the AniList id, which both sides came from - never on the title."""
    async with get_sessionmaker()() as session:
        subject = await _series(session, "Subject")
        owned = await _series(session, "Already Owned")
        await session.execute(
            text(
                """
                insert into list_entry
                    (provider, provider_media_id, series_id, title_romaji, synonyms,
                     status, user_progress_chapter, raw)
                values
                    ('anilist', '85486', :owned, 'Already Owned', '[]'::jsonb,
                     'reading', 0, '{}'::jsonb)
                """
            ),
            {"owned": owned},
        )
        await session.execute(
            text("update series set meta = cast(:meta as jsonb) where id = :id"),
            {
                "id": subject,
                "meta": (
                    '{"enrichment": {"similar": ['
                    '{"title": "Already Owned", "media_id": "85486"},'
                    '{"title": "Not Owned", "media_id": "999999"}'
                    "]}}"
                ),
            },
        )
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        body = (await http.get(f"/api/series/{subject}")).json()

    similar = {item["title"]: item for item in body["metadata"]["similar"]}
    assert similar["Already Owned"]["series_id"] == owned
    assert similar["Not Owned"]["series_id"] is None


async def test_the_reader_link_base_is_empty_until_it_is_configured():
    """komga_url is the compose-network address and is useless in a browser.

    An unset public URL has to reach the screen as an empty string so it offers
    no link at all, rather than one that lands on a host the reader cannot see.
    """
    async with get_sessionmaker()() as session:
        series_id = await _series(session, "Unconfigured")
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        body = (await http.get(f"/api/series/{series_id}")).json()

    assert body["komga_public_url"] == ""


async def test_a_configured_reader_link_base_loses_its_trailing_slash():
    """The screen joins it to `/book/<id>/read`, and `//book` is a 404."""
    async with get_sessionmaker()() as session:
        series_id = await _series(session, "Configured")
        await session.execute(
            text(
                """
                insert into setting (key, value) values ('komga_public_url', :value)
                on conflict (key) do update set value = excluded.value
                """
            ),
            {"value": "https://komga.test/"},
        )
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        body = (await http.get(f"/api/series/{series_id}")).json()

    assert body["komga_public_url"] == "https://komga.test"

    async with get_sessionmaker()() as session:
        await session.execute(text("delete from setting where key = 'komga_public_url'"))
        await session.commit()


async def test_the_settings_screen_can_edit_the_komga_address():
    """A key the settings route never lists is a field nobody can fill in.

    The detail screen reads this value and offers no reader links while it is
    empty, so a writable key that the screen cannot show is the same as the
    feature not existing.
    """
    from app import settings_store
    from app.api.routes_settings import EDITABLE

    assert settings_store.KOMGA_PUBLIC_URL in EDITABLE

    async with get_sessionmaker()() as session:
        values = await settings_store.all_settings(session)

    assert settings_store.KOMGA_PUBLIC_URL in values
