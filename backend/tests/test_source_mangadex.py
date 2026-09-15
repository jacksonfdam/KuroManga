"""MangaDexSource.list_pages, and the chapter it lets through end to end.

The at-home contract (base URL, chapter hash, data filenames) is read from
MangaDex's own API documentation (api.mangadex.org/docs, "Retrieving a
Chapter", read 2026-09-15), not from memory - the repository rule that has
already been applied to every other provider contract (CLAUDE.md, "Gotchas
learned the hard way").
"""

import zipfile
from decimal import Decimal

import httpx
import pytest

from app.downloader.cbz import write_cbz
from app.downloader.comicinfo import ComicInfo
from app.downloader.fetcher import fetch_pages
from app.sources.base import ChapterUnavailable
from app.sources.mangadex import API_BASE, MangaDexSource
from app.sources.net import CatalogueRow, SiteClient

CHAPTER_ID = "0aaf8b27-0013-4ae0-8935-91a089466874"
CHAPTER_URL = f"https://mangadex.org/chapter/{CHAPTER_ID}"


def _source(handler) -> MangaDexSource:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return MangaDexSource(client=client)


async def test_list_pages_calls_the_documented_at_home_endpoint(fixture):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=fixture("mangadex_at_home.json"))

    pages = await _source(handler).list_pages(CHAPTER_URL)

    assert seen["url"] == f"{API_BASE}/at-home/server/{CHAPTER_ID}"
    assert len(pages) == 15
    assert pages[0].url.endswith(
        "1-fefb667afaf589128da66a6a08dfd064c39d9d4c8ed9e30512de2b75d6908c6a.png"
    )


async def test_list_pages_raises_chapter_unavailable_for_a_missing_chapter():
    """The exact body MangaDex answers for an unknown id, recorded against the
    live service 2026-09-15 - result: error, one entry in errors with status 404.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "result": "error",
                "errors": [
                    {
                        "id": "770a6444-c695-570d-bfd2-a0eec2e95ce9",
                        "status": 404,
                        "title": "not_found_http_exception",
                        "detail": f"Chapter with ID {CHAPTER_ID} not found.",
                        "context": None,
                    }
                ],
            },
        )

    with pytest.raises(ChapterUnavailable):
        await _source(handler).list_pages(CHAPTER_URL)


async def test_a_server_error_is_not_mistaken_for_chapter_unavailable():
    """A 500 must retry through the normal ladder, not skip straight to
    PermanentError the way a 404 does.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="upstream hiccup")

    with pytest.raises(httpx.HTTPStatusError):
        await _source(handler).list_pages(CHAPTER_URL)


async def test_a_chapter_downloads_end_to_end_through_the_python_path(fixture, tmp_path):
    """list_pages -> fetch_pages -> write_cbz, the whole replacement for the
    deleted binary, run back to back against recorded page bytes.
    """
    at_home = fixture("mangadex_at_home.json")
    filenames = at_home["chapter"]["data"]
    page_bytes = {
        name: b"\xff\xd8\xff\xe0" + bytes([index]) * 16
        for index, name in enumerate(filenames)
    }

    def api_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=at_home)

    def cdn_handler(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=page_bytes[name])

    pages = await _source(api_handler).list_pages(CHAPTER_URL)

    row = CatalogueRow(key="mangadex-e2e-test", base_url=at_home["baseUrl"])
    client = SiteClient(row, transport=httpx.MockTransport(cdn_handler))
    fetched = await fetch_pages(client, pages)

    assert fetched == [page_bytes[name] for name in filenames]

    destination = tmp_path / "series" / "series - Ch.0001.cbz"
    await write_cbz(fetched, destination, ComicInfo(series="Escape Machine", number=Decimal("1")))

    with zipfile.ZipFile(destination) as archive:
        names = [n for n in archive.namelist() if n != "ComicInfo.xml"]
        assert len(names) == 15
        assert names == sorted(names)


async def test_a_chapter_hosted_elsewhere_is_unavailable():
    """MangaDex answers 200 with no pages when the chapter lives somewhere else.

    Black Clover chapter 1 is one: `externalUrl` points at MangaPlus and
    `attributes.pages` is 0. Read as a successful listing, it wrote an archive
    containing nothing but ComicInfo.xml and marked the chapter downloaded.
    """
    payload = {"result": "ok", "baseUrl": "https://example.test", "chapter": {"hash": "", "data": []}}

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    source = MangaDexSource(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(ChapterUnavailable, match="hosted elsewhere"):
        await source.list_pages("https://mangadex.org/chapter/65698b34-e7e1-4e42-8b79-a5bf6c8827b8")
