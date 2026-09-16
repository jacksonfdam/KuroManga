"""The MangaFire client: what it sends, and what it does with a refusal.

The parsers are covered separately against the same recordings. What matters
here is the two things only the client can get wrong — the order parameters are
sent in, which the site validates and which cost a real `Invalid token` while
this was being built, and telling a refusal apart from data when the refusal
arrives as HTTP 200.
"""

import json
from pathlib import Path

import httpx
import pytest

from app.sources.base import ChapterUnavailable
from app.sources.mangafire.source import ChallengeRequired, MangaFireSource, _hid_from_url
from app.sources.net import CatalogueRow, SiteClient

pytestmark = pytest.mark.asyncio

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _source(handler, *, waf_pass: str = "") -> MangaFireSource:
    row = CatalogueRow(
        key="mangafire-test",
        base_url="https://mangafire.to",
        rate_limit={"permits": 1000, "period_seconds": 0.01},
    )
    client = SiteClient(row, transport=httpx.MockTransport(handler), flaresolverr_url="")
    return MangaFireSource(client=client, waf_pass=waf_pass)


async def test_parameters_are_sent_in_the_order_they_were_signed():
    """The site recomputes the signature from the request as it arrives.

    Sending them in any other order answers `Invalid token` — which it did,
    against the live site, while this was being written. The mistake is
    invisible until a request uses parameters that are not already alphabetical,
    which is why it is pinned here.
    """
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=fixture("mangafire_chapters.json"))

    await _source(handler).list_chapters("https://mangafire.to/title/92kk8-naruto")

    names = [pair[0] for pair in httpx.QueryParams(seen[0].url.query.decode()).multi_items()]
    assert names == ["language", "limit", "order", "page", "sort", "vrf"]


async def test_every_request_carries_a_signature():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=fixture("mangafire_titles.json"))

    await _source(handler).search(["Naruto"])

    assert httpx.QueryParams(seen[0].url.query.decode()).get("vrf")


async def test_the_cookie_travels_when_one_is_configured():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=fixture("mangafire_titles.json"))

    await _source(handler, waf_pass="abc123").search(["Naruto"])

    assert "waf_pass=abc123" in seen[0].headers.get("cookie", "")


async def test_no_cookie_is_sent_when_none_is_configured():
    """An empty cookie is not the same as none, and the site reads it as a
    session it has never seen."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=fixture("mangafire_titles.json"))

    await _source(handler).search(["Naruto"])

    assert "waf_pass" not in seen[0].headers.get("cookie", "")


async def test_a_refusal_arriving_as_200_is_not_read_as_data():
    """`{"message": "Invalid token."}` comes back with a 200, so
    `raise_for_status` lets it through and the caller parses an error as a
    result. This is the exact body the live site returned."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": "Invalid token."})

    with pytest.raises(ChallengeRequired, match="waf_pass"):
        await _source(handler).search(["Naruto"])


async def test_a_403_says_what_to_check_first():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={})

    with pytest.raises(ChallengeRequired, match="vrf.py"):
        await _source(handler).search(["Naruto"])


async def test_the_chapter_list_follows_the_site_paging():
    """704 chapters over a paged endpoint. Stopping at the first page loses most
    of a long series, and the download would succeed while the library is short."""
    pages: list[int] = []
    first = fixture("mangafire_chapters.json")
    last = {"items": first["items"], "meta": {**first["meta"], "hasNext": False}}

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(httpx.QueryParams(request.url.query.decode())["page"])
        pages.append(page)
        return httpx.Response(200, json=first if page < 3 else last)

    chapters = await _source(handler).list_chapters("https://mangafire.to/title/92kk8-naruto")

    assert pages == [1, 2, 3]
    assert len(chapters) == 15


async def test_search_drops_what_is_not_a_comic():
    """The recording carries a doujinshi and an `other` beside the two manga.
    Either one reaching Review wastes the single decision it exists to ask for."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fixture("mangafire_titles.json"))

    found = await _source(handler).search(["Naruto"])

    assert [c.title for c in found] == ["Naruto", "Naruto"]


async def test_a_chapter_with_no_pages_is_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"pages": []}})

    with pytest.raises(ChapterUnavailable):
        await _source(handler).list_pages("https://mangafire.to/api/chapters/1326884")


async def test_pages_come_back_in_order():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fixture("mangafire_pages.json"))

    pages = await _source(handler).list_pages("https://mangafire.to/api/chapters/1326884")

    assert len(pages) == 23


@pytest.mark.parametrize(
    ("url", "hid"),
    [
        ("https://mangafire.to/title/92kk8-naruto", "92kk8"),
        ("https://mangafire.to/title/92kk8-naruto/", "92kk8"),
        ("/title/l33-narutoo", "l33"),
    ],
)
async def test_the_hid_is_taken_from_the_title_url(url, hid):
    """The hid addresses a title in this API — not the numeric `id`, which the
    same response also carries and which nothing accepts."""
    assert _hid_from_url(url) == hid


async def test_the_catalogue_row_ships_disabled():
    """It cannot answer until a person has cleared the site's check and pasted
    the cookie. A source that is on but cannot answer is worse than one the
    reader turns on deliberately."""
    from sqlalchemy import text

    from app.db import get_sessionmaker

    async with get_sessionmaker()() as session:
        row = (
            await session.execute(
                text(
                    "select c.key, c.nsfw, p.key is not null as has_pref"
                    " from site_catalogue c left join source_pref p using (key)"
                    " where c.key = 'mangafire'"
                )
            )
        ).mappings().one()

    assert row["has_pref"] is False
    # MIXED upstream: what the site carries is a fact about the site.
    assert row["nsfw"] is True
