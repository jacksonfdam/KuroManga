"""Komga client behaviour, from recorded responses and a stub transport."""

import json

import httpx
import pytest

from app.komga.client import KomgaClient, library_payload, parse_books, pick_series

pytestmark = pytest.mark.asyncio

REQUIRED_BY_KOMGA = {
    "analyzeDimensions", "convertToCbz", "emptyTrashAfterScan", "hashFiles", "hashKoreader",
    "hashPages", "importBarcodeIsbn", "importComicInfoBook", "importComicInfoCollection",
    "importComicInfoReadList", "importComicInfoSeries", "importComicInfoSeriesAppendVolume",
    "importEpubBook", "importEpubSeries", "importLocalArtwork", "importMylarSeries", "name",
    "repairExtensions", "root", "scanCbx", "scanDirectoryExclusions", "scanEpub",
    "scanForceModifiedTime", "scanInterval", "scanOnStartup", "scanPdf", "seriesCover",
}


def test_library_payload_states_every_field_komga_requires():
    assert REQUIRED_BY_KOMGA <= set(library_payload("Manga", "/manga"))


def test_library_payload_turns_on_comicinfo_import():
    payload = library_payload("Manga", "/manga")
    assert payload["importComicInfoBook"] is True
    assert payload["importComicInfoSeries"] is True


def test_library_payload_leaves_the_archives_alone():
    payload = library_payload("Manga", "/manga")
    assert payload["convertToCbz"] is False
    assert payload["repairExtensions"] is False


def test_books_carry_read_progress(fixture):
    books = parse_books(fixture("komga_books.json"))
    assert [book.completed for book in books] == [True, False, False]
    assert books[0].page == 20


def test_a_book_without_progress_is_not_read(fixture):
    assert parse_books(fixture("komga_books.json"))[2].completed is False


def test_book_filename_is_the_path_tail(fixture):
    assert parse_books(fixture("komga_books.json"))[0].filename == (
        "escape-machine - Ch.0001.cbz"
    )


def test_series_is_matched_by_folder_not_by_title(fixture):
    found = pick_series(fixture("komga_series.json"), "/manga", "escape-machine")
    assert found["id"] == "series-1"


def test_a_similar_folder_name_is_not_a_match(fixture):
    assert pick_series(fixture("komga_series.json"), "/manga", "escape") is None


async def test_an_api_key_is_sent_as_a_header():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, json={"isClaimed": True})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = KomgaClient("http://komga", api_key="secret-key", client=http_client)
        assert await client.is_claimed() is True
    assert seen["x-api-key"] == "secret-key"
    assert "authorization" not in seen


async def test_basic_auth_is_used_when_no_key_is_configured():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, json={"isClaimed": False})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = KomgaClient("http://komga", user="me", password="pw", client=http_client)
        assert await client.is_claimed() is False
    assert "authorization" in seen
    assert "x-api-key" not in seen


async def test_a_client_without_credentials_says_so():
    assert KomgaClient("http://komga").has_credentials is False
    assert KomgaClient("http://komga", api_key="k").has_credentials is True


async def test_claim_sends_the_headers_komga_expects():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/claim") and request.method == "GET":
            return httpx.Response(200, json={"isClaimed": False})
        captured.update(request.headers)
        return httpx.Response(200, json={"id": "user-1"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = KomgaClient("http://komga", user="me@example.test", password="pw",
                             client=http_client)
        assert await client.claim("me@example.test", "pw") is True
    assert captured["x-komga-email"] == "me@example.test"
    assert captured["x-komga-password"] == "pw"


async def test_an_existing_library_is_reused_rather_than_duplicated():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.method == "GET":
            return httpx.Response(
                200, json=[{"id": "lib-1", "name": "Manga", "root": "/manga/"}]
            )
        return httpx.Response(200, json={"id": "lib-new"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = KomgaClient("http://komga", api_key="k", client=http_client)
        assert await client.ensure_library("Manga", "/manga") == "lib-1"
    assert not any(call.startswith("POST") for call in calls)


async def test_a_missing_library_is_created_with_the_configured_root():
    body: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=[])
        body.update(json.loads(request.content))
        return httpx.Response(200, json={"id": "lib-new"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = KomgaClient("http://komga", api_key="k", client=http_client)
        assert await client.ensure_library("Manga", "/manga") == "lib-new"
    assert body["root"] == "/manga"
