"""The user's own note on a series, written wherever a provider keeps one.

AniList calls it MediaList.notes; MyAnimeList calls it my_list_status.comments
and also has free tags, which AniList does not. A provider that keeps neither
is skipped, not failed - one provider without the field must not stop the note
reaching the one that has it.
"""

import json
from typing import Any

from sqlalchemy import text

from app.enums import JobType, Provider
from app.handlers.base import JobContext, PermanentError, latest_payload, register
from app.providers import get_source
from app.providers.base import NotSupported
from app.providers.tokens import NotConnected, access_token_for


async def latest_requested(ctx: JobContext, series_id: int) -> dict[str, Any] | None:
    """The note and tags the most recently queued or leased write for this
    series carries. See base.latest_payload for why "latest" is the right
    rule."""
    payload = await latest_payload(ctx, JobType.NOTES_WRITE, series_id)
    if payload is None:
        return None
    return {"notes": payload.get("notes"), "tags": payload.get("tags") or []}


@register(JobType.NOTES_WRITE)
async def handle(ctx: JobContext) -> None:
    series_id = int(ctx.payload["series_id"])
    latest = await latest_requested(ctx, series_id) or ctx.payload
    notes = str(latest.get("notes") or "")
    tags = [str(tag) for tag in latest.get("tags") or []]

    result = await ctx.session.execute(
        text(
            """
            select e.id, e.provider, e.provider_media_id,
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
            await ctx.log(f"{entry.provider} is not connected; skipped", level="warning")
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
        # The local row follows the provider write, not the click: list_sync
        # only runs every six hours, and without this the API would keep
        # answering with the note the user just replaced until then, which
        # reads as the save having been lost. The next sync overwrites this
        # with the provider's own copy regardless, so this is a stand-in for
        # that copy, not a second record of it drifting alongside.
        await _store_note_locally(ctx, entry.id, entry.provider, notes, tags)
        written += 1
        await ctx.log(f"note written to {entry.provider}")

    if written == 0:
        raise PermanentError(f"series {series_id}: no list keeps a note")


async def _store_note_locally(
    ctx: JobContext, entry_id: int, provider: str, notes: str, tags: list[str]
) -> None:
    """Write the note into `list_entry.raw` at the key `series_metadata.py` reads.

    Each provider nests it differently: AniList carries `notes` at the top of
    the entry, MyAnimeList under `list_status.comments` (and `list_status.tags`
    for the personal tags AniList has no equivalent of). A provider this
    handler does not recognise is left untouched rather than guessed at.
    """
    if provider == str(Provider.ANILIST):
        await ctx.session.execute(
            text(
                """
                update list_entry
                   set raw = jsonb_set(raw, '{notes}', cast(:notes as jsonb))
                 where id = :id
                """
            ),
            {"notes": json.dumps(notes), "id": entry_id},
        )
    elif provider == str(Provider.MAL):
        # jsonb_set only ever creates the final path segment, not an absent
        # parent: an entry synced before `list_status` existed on it (or one
        # whose raw was flattened by an older code path) has no such object,
        # and the plain nested jsonb_set below would silently write nothing.
        # The inner jsonb_set materialises `{list_status}` first, defaulting
        # to `{}` when it is not already there, so the write always lands.
        await ctx.session.execute(
            text(
                """
                update list_entry
                   set raw = jsonb_set(
                           jsonb_set(
                               jsonb_set(raw, '{list_status}', coalesce(raw -> 'list_status', '{}'::jsonb)),
                               '{list_status,comments}', cast(:notes as jsonb)
                           ),
                           '{list_status,tags}', cast(:tags as jsonb)
                       )
                 where id = :id
                """
            ),
            {"notes": json.dumps(notes), "tags": json.dumps(tags), "id": entry_id},
        )
