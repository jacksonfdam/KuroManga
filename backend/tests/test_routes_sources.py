"""The source catalogue as the settings screen reads and writes it."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client


@pytest.fixture(autouse=True)
async def extra_row():
    """A row the v1 migration does not seed: a template with no implementation,
    in another language, carrying a content warning. One row exercises the
    language filter, the nsfw filter and the "cannot run" reason at once.
    """
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                "insert into site_catalogue"
                " (key, name, template, base_url, lang, nsfw, overrides, version, hand_ported)"
                " values ('nihonsite', 'Nihon Site', 'madara', 'https://nihon.example', 'ja',"
                " true, '{}'::jsonb, '1.0.0', false)"
                " on conflict (key) do nothing"
            )
        )
        await session.commit()
    yield
    async with get_sessionmaker()() as session:
        await session.execute(text("delete from source_pref where key = 'nihonsite'"))
        await session.execute(text("delete from site_catalogue where key = 'nihonsite'"))
        await session.commit()


async def test_the_listing_pages_and_reports_the_real_total(client):
    body = (await client.get("/api/sources?size=1")).json()

    assert len(body["items"]) == 1
    # The screen must not report its page as the total: the catalogue is
    # generated output that grows to four figures, and a count of what fitted on
    # one page is a different number entirely.
    assert body["total"] > 1
    assert body["size"] == 1
    assert body["page"] == 1


async def test_a_row_that_cannot_run_says_why(client):
    items = {i["key"]: i for i in (await client.get("/api/sources?size=100")).json()["items"]}

    # Two different answers, and the screen invents neither of them.
    assert items["nihonsite"]["reason"] == "not hand-ported"
    assert items["thunderscans"]["reason"] is None


async def test_a_template_with_no_implementation_says_so(client):
    async with get_sessionmaker()() as session:
        await session.execute(
            text("update site_catalogue set hand_ported = true where key = 'nihonsite'")
        )
        await session.commit()

    items = {i["key"]: i for i in (await client.get("/api/sources?size=100")).json()["items"]}

    assert items["nihonsite"]["reason"] == "no implementation for the madara template"


async def test_filters_narrow_by_language_and_content_warning(client):
    japanese = (await client.get("/api/sources?lang=ja&size=100")).json()["items"]
    safe = (await client.get("/api/sources?nsfw=false&size=100")).json()["items"]

    assert {i["key"] for i in japanese} == {"nihonsite"}
    assert "nihonsite" not in {i["key"] for i in safe}
    assert "thunderscans" in {i["key"] for i in safe}


async def test_search_matches_the_name_and_the_key(client):
    by_name = (await client.get("/api/sources?q=thunder&size=100")).json()["items"]
    by_key = (await client.get("/api/sources?q=nihonsite&size=100")).json()["items"]

    assert "thunderscans" in {i["key"] for i in by_name}
    assert {i["key"] for i in by_key} == {"nihonsite"}


async def test_toggling_a_source_persists(client):
    response = await client.put("/api/sources/nihonsite", json={"enabled": True})

    assert response.status_code == 200
    assert response.json()["enabled"] is True

    async with get_sessionmaker()() as fresh:
        stored = (
            await fresh.execute(
                text("select enabled from source_pref where key = 'nihonsite'")
            )
        ).scalar_one()
    assert stored is True


async def test_toggling_a_site_the_catalogue_does_not_carry_is_a_404(client):
    response = await client.put("/api/sources/no-such-site", json={"enabled": True})

    assert response.status_code == 404
    # Asserts the handler's own words, so this fails if the route is deleted
    # rather than passing on FastAPI's default for an unknown path.
    assert "no-such-site" in response.json()["detail"]
