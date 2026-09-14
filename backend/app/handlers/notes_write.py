"""The user's own note on a series, written wherever a provider keeps one.

AniList calls it MediaList.notes; MyAnimeList calls it my_list_status.comments
and also has free tags, which AniList does not. A provider that keeps neither
is skipped, not failed - one provider without the field must not stop the note
reaching the one that has it.
"""

from sqlalchemy import text

from app.enums import JobType, Provider
from app.handlers.base import JobContext, PermanentError, register
from app.providers import get_source
from app.providers.base import NotSupported
from app.providers.tokens import NotConnected, access_token_for


@register(JobType.NOTES_WRITE)
async def handle(ctx: JobContext) -> None:
    series_id = int(ctx.payload["series_id"])
    notes = str(ctx.payload.get("notes") or "")
    tags = [str(tag) for tag in ctx.payload.get("tags") or []]

    result = await ctx.session.execute(
        text(
            """
            select e.provider, e.provider_media_id,
                   t.provider is not null as connected
              from list_entry e
              left join provider_token t on t.provider = e.provider
             where e.series_id = :series_id
            """
        ),
        {"series_id": series_id},
    )
    entries = result.all()
    if not any(entry.connected for entry in entries):
        raise PermanentError(f"series {series_id} has no connected list entry")

    written = 0
    for entry in entries:
        if not entry.connected:
            continue
        try:
            token = await access_token_for(ctx.session, Provider(entry.provider))
        except NotConnected as failure:
            await ctx.log(f"{entry.provider}: {failure}", level="warning")
            continue
        try:
            await get_source(Provider(entry.provider)).set_notes(
                token, entry.provider_media_id, notes, tags
            )
        except NotSupported as failure:
            await ctx.log(str(failure), level="warning")
            continue
        written += 1
        await ctx.log(f"note written to {entry.provider}")

    if written == 0:
        raise PermanentError(f"series {series_id}: no list keeps a note")
