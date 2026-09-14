"""A list status the user set on the detail screen, pushed to every list.

Separate from PROGRESS_WRITE because the product brief's rule is that a status
write never carries progress, and two jobs cannot blur into one the way two
branches of one job can. Separate from LIST_WRITE because that one is scoped to
a suggestion being approved, not to a series already in the library.

Writing a status is idempotent, which is what makes a retry free.
"""

from sqlalchemy import text

from app.enums import JobType, ListStatus, Provider
from app.handlers.base import JobContext, PermanentError, latest_payload, register
from app.providers import get_source
from app.providers.tokens import NotConnected, access_token_for


async def latest_requested(ctx: JobContext, series_id: int) -> str | None:
    """The status the most recently queued or leased write for this series
    carries. See base.latest_payload for why "latest" is the right rule."""
    payload = await latest_payload(ctx, JobType.STATUS_WRITE, series_id)
    return payload.get("status") if payload else None


@register(JobType.STATUS_WRITE)
async def handle(ctx: JobContext) -> None:
    series_id = int(ctx.payload["series_id"])
    status = ListStatus(await latest_requested(ctx, series_id) or ctx.payload["status"])

    # A left join, so an entry whose provider has no stored token is still seen:
    # joining it away would let the job report success while never attempting
    # half of the user's lists.
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
        await get_source(Provider(entry.provider)).set_status(
            token, entry.provider_media_id, status
        )
        # The local row follows the write, not the click: a status that never
        # reached the provider must not read as synced on the next page load.
        await ctx.session.execute(
            # updated_at is bumped explicitly. Its onupdate is an ORM default
            # and this is raw SQL, so without it the row keeps its old
            # timestamp — and the library shows whichever entry was updated most
            # recently, which is then a provider nothing ever wrote to. The
            # write lands in the database and the screen does not move.
            text(
                "update list_entry set status = :status, updated_at = now() "
                "where id = :id"
            ),
            {"status": str(status), "id": entry.id},
        )
        written += 1
        await ctx.log(f"{entry.provider} set to {status}")

    if written == 0:
        raise PermanentError(f"series {series_id}: no list accepted the status")
