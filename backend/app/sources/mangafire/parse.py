"""Readers for MangaFire's JSON, kept pure so they can be tested from recordings.

Every shape here was read from a real response recorded on 2026-09-16, not from
the Kotlin DTOs. The two are close but not identical, and a parser written from
the DTO of a client that is not this one is how this project has twice shipped
something that only failed against the live service.
"""

from decimal import Decimal, InvalidOperation
from typing import Any

from app.sources.base import Candidate, ChapterRef, PageRef
from app.text_utils import best_similarity

SITE = "mangafire"
BASE_URL = "https://mangafire.to"

# `type` on a title. The site carries more than comics, and a doujinshi or a
# novel reaching the review screen as a candidate wastes the one decision the
# screen exists to ask for.
COMIC_TYPES = {"manga", "manhwa", "manhua", "one_shot", "oneshot", "comic"}


def parse_titles(payload: dict[str, Any], titles: list[str]) -> list[Candidate]:
    """Search results, best match first.

    `hid` rather than `id` is what identifies a title everywhere else in this
    API - the chapter list is addressed by it - so the candidate URL is built
    from `url`, which already carries it.
    """
    candidates: list[Candidate] = []
    for item in payload.get("items") or []:
        name = item.get("title")
        if not name:
            continue
        url = item.get("url")
        if not url:
            continue
        poster = item.get("poster") or {}
        candidates.append(
            Candidate(
                source_site=SITE,
                source_url=f"{BASE_URL}{url}",
                title=name,
                cover_url=poster.get("large") or poster.get("medium"),
                chapter_count=_int_or_none(item.get("latestChapter")),
                year=_int_or_none(item.get("year")),
                # (candidates, target), the same way as mangadex.py: the
                # names this source offers, scored against each title the
                # library knows the series by.
                score=max((best_similarity([name], t) for t in titles), default=0.0),
                alt_titles=[],
            )
        )
    return sorted(candidates, key=lambda c: c.score, reverse=True)


def parse_chapters(payload: dict[str, Any]) -> list[ChapterRef]:
    """One page of a title's chapter list.

    `number` arrives as a number rather than a string, and the site publishes
    fractional chapters, so it is read through Decimal rather than int.
    """
    chapters: list[ChapterRef] = []
    for item in payload.get("items") or []:
        number = _decimal_or_none(item.get("number"))
        if number is None:
            continue
        chapter_id = item.get("id")
        if chapter_id is None:
            continue
        chapters.append(
            ChapterRef(
                number=number,
                url=f"{BASE_URL}/api/chapters/{chapter_id}",
                title=item.get("name") or None,
                language=item.get("language") or "en",
            )
        )
    return chapters


def has_next(payload: dict[str, Any]) -> bool:
    """Whether another page of chapters follows.

    Naruto answers 704 chapters over 141 pages at the size the site chose, so a
    reader that takes only the first page silently loses most of a long series.
    """
    return bool((payload.get("meta") or {}).get("hasNext"))


def parse_pages(payload: dict[str, Any]) -> list[PageRef]:
    """The images of one chapter, in reading order.

    No per-page headers. The recording shows plain CDN URLs on a different host
    from the site, and inventing a referer the service did not ask for would be
    noise - the field is there for the sites that do demand one.
    """
    data = payload.get("data") or {}
    return [
        PageRef(url=page["url"]) for page in data.get("pages") or [] if page.get("url")
    ]


def cross_references(payload: dict[str, Any]) -> dict[str, str]:
    """The provider ids a chapter response carries for its title.

    MangaFire states MyAnimeList and AniList ids directly, which is a stronger
    link to a list entry than any title comparison this project does. Empty
    strings are how the site says "none", so they are dropped rather than
    stored as a blank id that later reads as a real one.
    """
    title = (payload.get("data") or {}).get("title") or {}
    found = {
        "mal": title.get("malId") or "",
        "anilist": title.get("anilistId") or "",
        "mangabaka": title.get("mangabakaId") or "",
    }
    return {provider: value for provider, value in found.items() if value}


def is_comic(item: dict[str, Any]) -> bool:
    return (item.get("type") or "").lower() in COMIC_TYPES


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _decimal_or_none(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return None
