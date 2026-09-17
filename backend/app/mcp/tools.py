"""The pipeline, as seven tools.

Everything here is written for a model with a small context window, which is
what two rules in this module are for.

**Fields are selected, never forwarded.** `GET /api/series` answers with
everything the Library grid draws — score, genres, format, read progress, cover
URLs — and a column added there would otherwise inflate every response here
until the budget below was quietly gone.

**Every response is measured.** `RESPONSE_BUDGET` is asserted in the tests
rather than hoped for: a list tool trims its own list and says so instead of
handing a 300-title payload to a model with eight thousand tokens to spend.
"""

import json
from typing import Any

from app.mcp.api import SoshuhenApi

# Bytes of JSON one tool may answer with. Around a thousand tokens, so a model
# can hold several turns of this conversation and still have room to act on it.
RESPONSE_BUDGET = 4096

DEFAULT_SERIES_LIMIT = 20
MAX_SERIES_LIMIT = 50
DEFAULT_REVIEW_LIMIT = 10
DEFAULT_CANDIDATE_LIMIT = 5
DEFAULT_FAILURE_LIMIT = 5

# The states `GET /api/series` derives, stated here so a tool can refuse an
# unknown one by name instead of answering with an empty list that reads like
# "nothing matches" rather than "that is not a state".
SERIES_STATES = ("needs_review", "mapped", "downloading", "failed")

# The widest span of chapter numbers one call may queue. Both bounds null means
# "every missing chapter" to the API, which is what once queued tens of
# thousands of chapters and filled fifteen gigabytes. A human clicking that
# button had seen the Library first; a model can hallucinate an argument, so the
# span is bounded here and a whole backlog stays reachable only through
# set_follow, the opt-in that is already visible on the screen.
MAX_CHAPTER_SPAN = 50

# Long enough to name the failure, short enough that five of them fit.
ERROR_EXCERPT = 160


def error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    """A refusal the model reads as data rather than as a sentence."""
    return {"ok": False, "error": code, "message": message, **extra}


def _budgeted(payload: dict[str, Any], key: str) -> dict[str, Any]:
    """Drop items from `payload[key]` until the response fits the budget."""
    items = payload[key]
    while len(json.dumps(payload)) > RESPONSE_BUDGET and items:
        items.pop()
        payload["truncated"] = True
    payload.setdefault("truncated", False)
    payload["returned"] = len(items)
    return payload


def _bounded(limit: int, ceiling: int) -> int:
    return max(1, min(int(limit), ceiling))


def _series_record(row: dict[str, Any]) -> dict[str, Any]:
    """One series, in the fields a decision about it needs and no others."""
    return {
        "id": row["id"],
        "title": row["title"],
        "state": row["state"],
        "downloaded": row["downloaded"],
        "known": row["known"],
        "total_chapters": row["total_chapters"],
        "auto_download": row["auto_download"],
    }


async def list_series(
    api: SoshuhenApi, state: str | None = None, limit: int = DEFAULT_SERIES_LIMIT
) -> dict[str, Any]:
    """Series with their state and chapter counts."""
    if state is not None and state not in SERIES_STATES:
        return error("unknown_state", f"state must be one of {', '.join(SERIES_STATES)}")
    rows = await api.get("/api/series", {"state": state})
    series = [_series_record(row) for row in rows[: _bounded(limit, MAX_SERIES_LIMIT)]]
    return _budgeted({"ok": True, "total": len(rows), "series": series}, "series")


def _candidate_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_site": row["source_site"],
        "source_url": row["source_url"],
        "title": row["title"],
        "year": row["year"],
        "chapters": row["chapter_count"],
        "score": round(float(row["score"]), 3),
    }


async def review_queue(
    api: SoshuhenApi,
    series_id: int | None = None,
    refresh: bool = False,
    limit: int = DEFAULT_REVIEW_LIMIT,
) -> dict[str, Any]:
    """Series awaiting a mapping, or one series' candidates.

    `refresh` re-runs the source search for one series, so a series whose
    candidate list comes back empty is not a dead end — which is the whole
    review loop's only escape hatch and the reason this is an argument rather
    than an eighth tool for a small model to hold.
    """
    if series_id is None:
        if refresh:
            return error("series_required", "refresh needs a series_id")
        queue = await api.get("/api/series/review/queue")
        pending = [
            {"id": item["id"], "title": item["title"], "candidates": item["candidate_count"]}
            for item in queue["items"][: _bounded(limit, MAX_SERIES_LIMIT)]
        ]
        return _budgeted({"ok": True, "total": queue["total"], "pending": pending}, "pending")

    search_job = None
    if refresh:
        search_job = (await api.post(f"/api/series/{series_id}/search"))["job_id"]

    payload = await api.get(f"/api/series/{series_id}/candidates")
    candidates = [
        _candidate_record(row)
        for row in payload["candidates"][: _bounded(limit, DEFAULT_CANDIDATE_LIMIT)]
    ]
    answer: dict[str, Any] = {
        "ok": True,
        "series_id": payload["series"]["id"],
        "title": payload["series"]["title"],
        "candidates": candidates,
    }
    if search_job is not None:
        # The search is a queued job, so the list below is still the old one.
        # Said plainly, because a model reading an empty list after asking for a
        # refresh would otherwise conclude the series has no source at all.
        answer["search_job_id"] = search_job
        answer["note"] = "search queued; call again once it finishes for new candidates"
    return _budgeted(answer, "candidates")


def _failure_record(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": job["id"],
        "type": job["type"],
        "series": job["series_title"],
        "permanent": job["permanent"],
        "error": (job["last_error"] or "")[:ERROR_EXCERPT] or None,
    }


async def jobs_status(
    api: SoshuhenApi, failures: int = DEFAULT_FAILURE_LIMIT
) -> dict[str, Any]:
    """Queue counts and worker state, plus recent failures with their error.

    Read from `/api/dashboard`, which answers all of it in one request: two
    calls to compose the same figures cost a small context window twice.
    """
    dashboard = await api.get("/api/dashboard")
    failed = await api.get("/api/jobs", {"state": "failed", "limit": _bounded(failures, 20)})
    return _budgeted(
        {
            "ok": True,
            "queue": dashboard["queue"],
            "worker": {
                "state": dashboard["worker"]["state"],
                "running": dashboard["worker"]["running"],
            },
            "downloads": {
                "in_flight": dashboard["downloads"]["in_flight"],
                "queued": dashboard["downloads"]["queued"],
                "failed_24h": dashboard["downloads"]["failed_24h"],
            },
            "awaiting_review": dashboard["mappings"]["pending"],
            "failures": [_failure_record(job) for job in failed],
        },
        "failures",
    )



async def confirm_mapping(api: SoshuhenApi, series_id: int, source_url: str) -> dict[str, Any]:
    """Confirm which source URL a series is, which releases it into the pipeline."""
    answer = await api.post(f"/api/series/{series_id}/mapping", {"source_url": source_url})
    return {"ok": True, "job_id": answer["job_id"]}


async def download_chapters(
    api: SoshuhenApi, series_id: int, from_chapter: float, to_chapter: float | None = None
) -> dict[str, Any]:
    """Queue a bounded range of chapters for one series.

    Both bounds are always sent. The endpoint reads a null bound as "every
    missing chapter", so an argument this tool failed to state would queue a
    whole backlog on a model's guess; a whole backlog is reachable through
    set_follow instead, which is the opt-in already visible in the Library.
    """
    start = float(from_chapter)
    ceiling = start + MAX_CHAPTER_SPAN
    end = ceiling if to_chapter is None else float(to_chapter)
    if end < start:
        return error("bad_range", "to_chapter is below from_chapter")

    capped = end > ceiling
    end = min(end, ceiling)
    answer = await api.post(
        f"/api/series/{series_id}/download", {"from_chapter": start, "to_chapter": end}
    )
    result = {
        "ok": True,
        "queued": answer["queued"],
        "from_chapter": start,
        "to_chapter": end,
        "capped": capped,
    }
    if capped:
        result["note"] = (
            f"at most {MAX_CHAPTER_SPAN} chapters per call; "
            "call again from the next number, or use set_follow for the whole backlog"
        )
    return result


async def set_follow(api: SoshuhenApi, series_id: int, enabled: bool) -> dict[str, Any]:
    """Turn automatic downloading on or off for one series.

    On queues whatever is already missing, which is the deliberate way to fetch a
    whole backlog.
    """
    answer = await api.post(f"/api/series/{series_id}/auto-download", {"enabled": enabled})
    return {"ok": True, "auto_download": answer["auto_download"], "queued": answer["queued"]}


async def sync_lists(api: SoshuhenApi, provider: str) -> dict[str, Any]:
    """Trigger a list sync for one provider.

    The valid providers are read from the API rather than stated in this tool's
    schema: a hardcoded pair would start refusing a real provider the day a third
    one is added, and the refusal would read as a model error rather than a stale
    list.
    """
    settings = await api.get("/api/settings")
    providers = sorted(settings["providers"])
    if provider not in providers:
        return error(
            "unknown_provider",
            f"provider must be one of {', '.join(providers)}",
            providers=providers,
        )
    answer = await api.post(f"/api/sync/{provider}")
    return {"ok": True, "job_id": answer["job_id"]}
