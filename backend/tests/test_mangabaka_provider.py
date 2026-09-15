"""MangaBaka library reading.

Two facts here were discovered against the live API and are pinned because
getting either wrong fails in a way that looks like something else: the key goes
in `X-API-Key`, and an entry is identified by `series_id` rather than by its own
`id`.
"""

import httpx
import pytest

from app.config import get_settings
from app.enums import ListStatus, Provider
from app.providers import get_source
from app.providers.base import NotSupported
from app.providers.mangabaka import MangaBakaSource, next_page, parse_library

pytestmark = pytest.mark.asyncio


def test_the_entry_is_identified_by_its_series_not_its_row(fixture):
    """Addressing by the entry's own id returns 404 on the live API."""
    entries = parse_library(fixture("mangabaka_library.json"))
    assert entries[0].media_id == "1238"


def test_verified_states_map_onto_the_shared_vocabulary(fixture):
    entries = parse_library(fixture("mangabaka_library.json"))
    assert entries[0].status is ListStatus.READING
    assert entries[1].status is ListStatus.PLAN_TO_READ


def test_an_unrecognised_state_does_not_break_the_sync(fixture):
    entries = parse_library(fixture("mangabaka_library.json"))
    assert entries[2].status is ListStatus.PLAN_TO_READ
    assert entries[2].raw["state"] == "some_future_state"


def test_progress_is_read_from_the_entry(fixture):
    assert parse_library(fixture("mangabaka_library.json"))[0].progress_chapter == 12


def test_total_chapters_arrives_as_a_string_and_becomes_a_number(fixture):
    assert parse_library(fixture("mangabaka_library.json"))[0].total_chapters == 40


def test_an_empty_total_chapters_becomes_none_not_an_empty_string(fixture):
    """Postgres types that column as an integer, so a stray "" fails at bind time."""
    assert parse_library(fixture("mangabaka_library.json"))[1].total_chapters is None


def test_a_missing_total_chapters_is_tolerated(fixture):
    assert parse_library(fixture("mangabaka_library.json"))[2].total_chapters is None


def test_titles_collect_every_spelling_the_series_carries(fixture):
    entry = parse_library(fixture("mangabaka_library.json"))[0]
    assert "Tousou Kikou" in entry.titles
    assert "Escape Machine" in entry.titles
    assert "逃走機構" in entry.titles
    assert "Escape Mechanism" in entry.titles


def test_a_series_without_extra_titles_still_parses(fixture):
    assert parse_library(fixture("mangabaka_library.json"))[1].titles == ["Quiet Sea"]


def test_a_cover_is_taken_when_present_and_skipped_when_not(fixture):
    entries = parse_library(fixture("mangabaka_library.json"))
    assert entries[0].cover_url == "https://images.example.test/raw.jpg"
    assert entries[1].cover_url is None
    assert entries[2].cover_url is None


def test_the_raw_entry_is_kept_so_cross_references_survive(fixture):
    entry = parse_library(fixture("mangabaka_library.json"))[0]
    assert entry.raw["Series"]["source"]["my_anime_list"]["id"] == 7001


def test_series_type_is_normalised_onto_the_shared_vocabulary(fixture):
    entries = parse_library(fixture("mangabaka_library.json"))
    assert entries[0].kind == "MANGA"
    assert entries[1].kind == "NOVEL"


def test_a_missing_series_type_is_not_a_claim_about_the_kind(fixture):
    """Issue #88: absent or unrecognised is silence, not evidence of prose."""
    assert parse_library(fixture("mangabaka_library.json"))[2].kind is None


def test_pagination_is_followed_by_link_not_by_counting(fixture):
    assert next_page(fixture("mangabaka_library.json")).endswith("page=2")


def test_the_last_page_stops_the_walk():
    assert next_page({"pagination": {"next": None}}) is None
    assert next_page({}) is None


async def test_the_key_goes_in_the_api_key_header_not_as_a_bearer_token(fixture):
    """Sent as a bearer token the API answers "Invalid access token"."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, json={"data": [], "pagination": {"next": None}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await MangaBakaSource(client).fetch_list("mb-secret")

    assert seen["x-api-key"] == "mb-secret"
    assert "authorization" not in seen


async def test_every_page_is_walked(fixture):
    pages = [
        {"data": [], "pagination": {"next": "https://api.mangabaka.org/v1/my/library?page=2"}},
        {"data": [], "pagination": {"next": None}},
    ]
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, json=pages[len(requested) - 1])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await MangaBakaSource(client).fetch_list("mb-secret")

    assert len(requested) == 2
    assert requested[1].endswith("page=2")


async def test_the_source_declares_itself_read_only_and_keyless():
    source = get_source(Provider.MANGABAKA)
    assert source.writable is False
    assert source.uses_oauth is False


async def test_writing_is_refused_while_the_source_is_read_only():
    with pytest.raises(NotImplementedError):
        await MangaBakaSource().push_progress("mb-secret", "1238", 5)


async def test_the_oauth_flow_is_refused_rather_than_silently_doing_nothing():
    with pytest.raises(NotSupported):
        MangaBakaSource().authorize_url("http://localhost/cb", "state", "verifier")


async def test_the_credential_comes_from_configuration(monkeypatch):
    monkeypatch.setenv("MANGABAKA_TOKEN", "mb-from-env")
    get_settings.cache_clear()
    assert MangaBakaSource.static_credential() == "mb-from-env"
    get_settings.cache_clear()


async def test_no_credential_configured_reports_none(monkeypatch):
    monkeypatch.setenv("MANGABAKA_TOKEN", "")
    get_settings.cache_clear()
    assert MangaBakaSource.static_credential() is None
    get_settings.cache_clear()
