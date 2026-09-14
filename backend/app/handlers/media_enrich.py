"""The per-media extras, cached on the series that needed them.

The list queries cannot carry characters, recommendations, rankings or a score
distribution - they are object graphs per media, and one list response holding
them for every entry is a response AniList declines to send. They are fetched
one series at a time instead, by this job, and kept on `series.meta` so that
opening a detail page twice costs one request rather than two.

Only AniList answers this: MyAnimeList has no characters for manga at all, and
everything else it reports already arrives with the list fields.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text

from app.enums import JobType, Provider
from app.handlers.base import JobContext, PermanentError, register
from app.providers import get_source
from app.providers.tokens import NotConnected, access_token_for

# Rankings and recommendations move over months, not hours. Two weeks is short
# enough that a climbing series is not stuck at a stale rank forever, and long
# enough that browsing the library does not spend the rate limit.
ENRICHMENT_MAX_AGE_DAYS = 14


def is_stale(enrichment: dict[str, Any] | None, now: datetime) -> bool:
    """A cache with no timestamp is stale: it predates this field and there is
    no way to tell how old it is."""
    stamp = (enrichment or {}).get("fetched_at")
    if not stamp:
        return True
    try:
        fetched = datetime.fromisoformat(stamp)
    except ValueError:
        return True
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=UTC)
    return now - fetched > timedelta(days=ENRICHMENT_MAX_AGE_DAYS)


@register(JobType.MEDIA_ENRICH)
async def handle(ctx: JobContext) -> None:
    series_id = int(ctx.payload["series_id"])
    result = await ctx.session.execute(
        text(
            """
            select provider_media_id
              from list_entry
             where series_id = :series_id and provider = :provider
             limit 1
            """
        ),
        {"series_id": series_id, "provider": str(Provider.ANILIST)},
    )
    media_id = result.scalar_one_or_none()
    if media_id is None:
        # Nothing to ask, and asking again later will not change that.
        raise PermanentError(f"series {series_id} has no AniList entry to enrich")

    try:
        token = await access_token_for(ctx.session, Provider.ANILIST)
    except NotConnected as failure:
        raise PermanentError(str(failure)) from failure

    detail = await get_source(Provider.ANILIST).fetch_media_detail(token, media_id)
    detail["fetched_at"] = datetime.now(UTC).isoformat()

    await ctx.session.execute(
        text(
            """
            update series
               set meta = jsonb_set(
                       coalesce(meta, '{}'::jsonb), '{enrichment}', cast(:detail as jsonb), true
                   )
             where id = :series_id
            """
        ),
        {"series_id": series_id, "detail": json.dumps(detail)},
    )
    await ctx.log(f"enriched series {series_id} from AniList media {media_id}")
