"""The review queue, and the flag that takes a series out of it.

One title no source carries used to sit at the front of a 168-series queue and
stop every other one from being answered. The queue is now a list with a
position, and "not interested" is a decision the user can give and take back.

The tests that matter most here are the negative ones: ignoring a series must
be invisible to the library list, to the download path and to Komga, or the
button quietly means something the user was never told it meant.
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


async def _series(session, title: str, slug: str) -> int:
    return (
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta, created_at)
                values (:title, :slug, true, '{"cover_url": "http://cover"}'::jsonb, now())
                returning id
                """
            ),
            {"title": title, "slug": slug},
        )
    ).scalar_one()


async def _candidate(session, series_id: int, url: str) -> None:
    await session.execute(
        text(
            """
            insert into series_candidate (series_id, source_site, source_url, title, score)
            values (:series_id, 'mangadex', :url, 'A candidate', 0.9)
            """
        ),
        {"series_id": series_id, "url": url},
    )


async def _mapping(session, series_id: int, url: str) -> None:
    await session.execute(
        text(
            """
            insert into source_mapping (series_id, source_site, source_url, active, confirmed_at)
            values (:series_id, 'mangadex', :url, true, now())
            """
        ),
        {"series_id": series_id, "url": url},
    )


async def _seed_three(session) -> tuple[int, int, int]:
    """Three unmapped series, deliberately inserted out of alphabetical order."""
    third = await _series(session, "Vinland Saga", "vinland-saga")
    first = await _series(session, "A Certain Magical Index", "a-certain-magical-index")
    second = await _series(session, "Dandadan", "dandadan")
    await session.commit()
    return first, second, third


async def test_the_queue_lists_every_unmapped_series_in_one_stable_order(client):
    async with get_sessionmaker()() as session:
        first, second, third = await _seed_three(session)

    body = (await client.get("/api/series/review/queue")).json()
    assert [item["id"] for item in body["items"]] == [first, second, third]
    # Asked twice, answered the same way: a position the user is shown is only
    # a position if the next request puts the same series there.
    again = (await client.get("/api/series/review/queue")).json()
    assert [item["id"] for item in again["items"]] == [first, second, third]


async def test_the_count_and_the_positions_agree(client):
    async with get_sessionmaker()() as session:
        await _seed_three(session)

    body = (await client.get("/api/series/review/queue")).json()
    assert body["total"] == 3
    # The screen numbers a series "n of total" out of this same list. A total
    # the list cannot account for is how a position lands past the end of it.
    assert body["total"] == len(body["items"])
    assert len({item["id"] for item in body["items"]}) == body["total"]


async def test_a_mapped_series_is_not_in_the_queue(client):
    async with get_sessionmaker()() as session:
        first, second, _ = await _seed_three(session)
        await _mapping(session, first, "https://mangadex.org/title/x")
        await session.commit()

    body = (await client.get("/api/series/review/queue")).json()
    assert first not in [item["id"] for item in body["items"]]
    assert second in [item["id"] for item in body["items"]]


async def test_the_queue_says_how_many_candidates_each_series_has(client):
    """The list the user scans has to show which entries are one click from done."""
    async with get_sessionmaker()() as session:
        first, second, _ = await _seed_three(session)
        await _candidate(session, first, "https://mangadex.org/title/a")
        await _candidate(session, first, "https://mangadex.org/title/b")
        await session.commit()

    counts = {
        item["id"]: item["candidate_count"]
        for item in (await client.get("/api/series/review/queue")).json()["items"]
    }
    assert counts[first] == 2
    assert counts[second] == 0


async def test_ignoring_takes_a_series_out_of_the_queue(client):
    async with get_sessionmaker()() as session:
        first, second, third = await _seed_three(session)

    assert (await client.post(f"/api/series/{first}/review-ignore")).status_code == 200

    queue = (await client.get("/api/series/review/queue")).json()
    assert [item["id"] for item in queue["items"]] == [second, third]
    assert queue["total"] == 2

    ignored = (await client.get("/api/series/review/ignored")).json()
    assert [item["id"] for item in ignored["items"]] == [first]
    assert ignored["total"] == 1


async def test_a_skipped_series_is_still_in_the_queue(client):
    """Skipping is a deferral the browser holds, not an answer the server stores.

    Nothing a skip does may reach this endpoint: the series has to come back,
    or "come back later" is a lie. The only two ways out of this list are
    confirming a mapping and saying you are not interested.
    """
    async with get_sessionmaker()() as session:
        first, second, third = await _seed_three(session)

    before = (await client.get("/api/series/review/queue")).json()
    # Whatever the screen does with a skip, it makes no request — so the queue
    # after one is the queue before it, series for series.
    after = (await client.get("/api/series/review/queue")).json()
    assert before == after
    assert {first, second, third} == {item["id"] for item in after["items"]}


async def test_ignoring_is_reversible(client):
    async with get_sessionmaker()() as session:
        first, second, third = await _seed_three(session)

    await client.post(f"/api/series/{first}/review-ignore")
    assert (await client.delete(f"/api/series/{first}/review-ignore")).status_code == 200

    queue = (await client.get("/api/series/review/queue")).json()
    # Back in its own place, not appended to the end: the order is the title
    # order, and an unignored series has no reason to have moved.
    assert [item["id"] for item in queue["items"]] == [first, second, third]
    assert (await client.get("/api/series/review/ignored")).json() == {"total": 0, "items": []}


async def test_ignoring_twice_is_not_two_different_states(client):
    async with get_sessionmaker()() as session:
        first, _, _ = await _seed_three(session)

    await client.post(f"/api/series/{first}/review-ignore")
    await client.post(f"/api/series/{first}/review-ignore")
    assert (await client.get("/api/series/review/ignored")).json()["total"] == 1


async def test_ignoring_a_series_that_is_not_there_is_a_404(client):
    assert (await client.post("/api/series/999999/review-ignore")).status_code == 404
    assert (await client.delete("/api/series/999999/review-ignore")).status_code == 404


async def test_the_library_list_cannot_tell_a_series_was_ignored(client):
    """The flag removes a series from one queue and from nothing else.

    The user was told the series stays in their library and on their lists, so
    the library payload has to come back byte for byte the same — not merely
    still contain the row.
    """
    async with get_sessionmaker()() as session:
        first, _, _ = await _seed_three(session)
        await session.execute(
            text(
                """
                insert into list_entry
                       (provider, provider_media_id, series_id, status,
                        user_progress_chapter, total_chapters, synonyms, raw, updated_at)
                values ('anilist', '1', :series_id, 'reading', 12, 40, '[]'::jsonb,
                        '{"genres": ["Action"]}'::jsonb, now())
                """
            ),
            {"series_id": first},
        )
        await session.commit()

    before = (await client.get("/api/series")).json()
    before_detail = (await client.get(f"/api/series/{first}")).json()
    await client.post(f"/api/series/{first}/review-ignore")

    assert (await client.get("/api/series")).json() == before
    assert (await client.get(f"/api/series/{first}")).json() == before_detail
    # Still counted as a missing mapping on the front page: it genuinely has
    # none, and the dashboard is reporting the pipeline, not the user's queue.
    assert (await client.get("/api/series?state=needs_review")).json() == before


async def test_an_ignored_series_still_downloads_when_it_is_mapped(client):
    """Nothing about the flag reaches the download path.

    Ignoring says "stop asking me to map this", not "never fetch this". A user
    who later confirms a mapping by hand — or a series the pipeline maps for
    them — has to download exactly as it would have.
    """
    async with get_sessionmaker()() as session:
        first, _, _ = await _seed_three(session)
        await _candidate(session, first, "https://mangadex.org/title/abc")
        await session.commit()

    await client.post(f"/api/series/{first}/review-ignore")

    mapping = await client.post(
        f"/api/series/{first}/mapping", json={"source_url": "https://mangadex.org/title/abc"}
    )
    assert mapping.status_code == 200

    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into chapter (series_id, number, state, discovered_at)
                values (:series_id, 1, 'known', now()), (:series_id, 2, 'known', now())
                """
            ),
            {"series_id": first},
        )
        await session.commit()

    queued = await client.post(f"/api/series/{first}/download", json={})
    assert queued.json()["queued"] > 0

    auto = await client.post(f"/api/series/{first}/auto-download", json={"enabled": True})
    assert auto.json()["auto_download"] is True

    # And it is out of the queue for the ordinary reason now — it has a mapping.
    # It leaves the Ignored tab with it: that tab is the way back into the
    # queue, and a mapped series has no way back to offer. The flag is still on
    # the row (see the test below); it is simply not what is keeping it out.
    assert (await client.get("/api/series/review/queue")).json()["total"] == 2
    assert (await client.get("/api/series/review/ignored")).json()["total"] == 0


async def test_confirming_a_mapping_does_not_clear_the_ignore_flag(client):
    """Two different facts, and neither answers the other.

    A series mapped after being ignored leaves the queue because it is mapped.
    If that mapping is ever undone, the user's "stop asking" still stands —
    they never took it back.
    """
    async with get_sessionmaker()() as session:
        first, _, _ = await _seed_three(session)

    await client.post(f"/api/series/{first}/review-ignore")
    await client.post(
        f"/api/series/{first}/mapping", json={"source_url": "https://mangadex.org/title/abc"}
    )

    async with get_sessionmaker()() as session:
        still = await session.execute(
            text("select review_ignored_at from series where id = :id"), {"id": first}
        )
        assert still.scalar_one() is not None
