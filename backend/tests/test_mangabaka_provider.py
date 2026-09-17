"""MangaBaka library reading.

Two facts here were discovered against the live API and are pinned because
getting either wrong fails in a way that looks like something else: the key goes
in `X-API-Key`, and an entry is identified by `series_id` rather than by its own
`id`.
"""

import json

import httpx
import pytest

from app.config import get_settings
from app.enums import ListStatus, Provider
from app.providers import get_source
from app.providers.base import NotSupported
from app.providers.mangabaka import (
    STATE_FOR_STATUS,
    MangaBakaSource,
    next_page,
    parse_library,
)

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


async def test_the_source_declares_itself_writable_and_keyless():
    source = get_source(Provider.MANGABAKA)
    assert source.writable is True
    assert source.uses_oauth is False


async def _capture(call) -> httpx.Request:
    """Run one write against a transport that answers instead of the network."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"status": 200, "data": [{"series_id": 1238,
                                                                 "action": "updated"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await call(MangaBakaSource(client))
    return seen[0]


async def test_a_write_goes_to_the_batch_path_because_it_creates_what_is_absent():
    """`PATCH /my/library/{series_id}` answers 404 for a series not in the library.

    `set_status` is contracted to create the entry when it is absent, and batch
    is the only path that creates or patches under one request. A batch of one
    is still a batch.
    """
    request = await _capture(lambda source: source.push_progress("mb-secret", "1238", 12))

    assert str(request.url) == "https://api.mangabaka.org/v1/my/library/batch"
    assert request.method == "POST"


async def test_the_key_goes_in_the_api_key_header_on_a_write_too():
    request = await _capture(lambda source: source.push_progress("mb-secret", "1238", 12))

    assert request.headers["x-api-key"] == "mb-secret"
    assert "authorization" not in request.headers


async def test_the_series_id_is_sent_as_a_number_not_a_string():
    """It is typed as an integer upstream; a quoted number is a validation error."""
    request = await _capture(lambda source: source.push_progress("mb-secret", "1238", 12))

    assert json.loads(request.content) == [{"series_id": 1238, "progress_chapter": 12}]


async def test_a_progress_write_names_no_other_field():
    """Everything the user recorded on the entry survives a progress write.

    Batch patches only the fields present, so naming a field here is what would
    blank their rating or their note.
    """
    request = await _capture(lambda source: source.push_progress("mb-secret", "1238", 12))

    assert set(json.loads(request.content)[0]) == {"series_id", "progress_chapter"}


async def test_on_hold_is_written_as_paused_which_is_the_only_spelling_accepted():
    """The write schema has no `on_hold`, though the read vocabulary is wider.

    Inverting STATUS_MAP would produce exactly the spellings the API rejects.
    """
    request = await _capture(
        lambda source: source.set_status("mb-secret", "1238", ListStatus.ON_HOLD)
    )

    assert json.loads(request.content) == [{"series_id": 1238, "state": "paused"}]


@pytest.mark.parametrize(
    ("status", "state"),
    [
        (ListStatus.READING, "reading"),
        (ListStatus.PLAN_TO_READ, "plan_to_read"),
        (ListStatus.COMPLETED, "completed"),
        (ListStatus.DROPPED, "dropped"),
    ],
)
async def test_every_status_the_pipeline_holds_has_a_state_the_api_accepts(status, state):
    request = await _capture(lambda source: source.set_status("mb-secret", "1238", status))

    assert json.loads(request.content)[0]["state"] == state


def test_no_status_is_left_without_a_mapping():
    """A status with no entry here would raise at write time, per series, silently."""
    assert set(STATE_FOR_STATUS) == set(ListStatus)


def test_every_state_written_is_one_the_api_schema_accepts():
    """From MangaBaka's OpenAPI document, which is where these came from."""
    assert set(STATE_FOR_STATUS.values()) <= {
        "considering",
        "completed",
        "dropped",
        "paused",
        "plan_to_read",
        "reading",
        "rereading",
    }


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
