"""A chapter the user recorded by hand, pushed to the lists.

progress_push derives progress from Komga. This is the other direction: a
number the user stated. It is a separate job from LIST_WRITE on purpose — the
product brief's rule is that a status write never carries progress, and two
jobs cannot blur into one the way two branches of one job can.

The forward-only guard is the same rule progress_push applies to Komga-derived
numbers: a list that already records more must never be lowered by us.
"""

from sqlalchemy import text

from app.enums import JobType, Provider
from app.handlers.base import JobContext, PermanentError, register
from app.providers import get_source
from app.providers.tokens import access_token_for


def forward_only(current: int, requested: int) -> int | None:
    """The chapter to write, or None when it would not move the list forward."""
    return requested if requested > current else None


@register(JobType.PROGRESS_WRITE)
async def handle(ctx: JobContext) -> None:
    series_id = int(ctx.payload["series_id"])
    chapter = int(ctx.payload["chapter"])

    result = await ctx.session.execute(
        text(
            """
            select e.id, e.provider, e.provider_media_id, e.user_progress_chapter
              from list_entry e
              join provider_token t on t.provider = e.provider
             where e.series_id = :series_id
            """
        ),
        {"series_id": series_id},
    )
    entries = result.all()
    if not entries:
        raise PermanentError(f"series {series_id} has no connected list entry")

    pushed = 0
    for entry in entries:
        target = forward_only(entry.user_progress_chapter, chapter)
        if target is None:
            await ctx.log(f"{entry.provider}: already at chapter {entry.user_progress_chapter}")
            continue
        provider = Provider(entry.provider)
        token = await access_token_for(ctx.session, provider)
        await get_source(provider).push_progress(token, entry.provider_media_id, target)
        await ctx.session.execute(
            text("update list_entry set user_progress_chapter = :n where id = :id"),
            {"n": target, "id": entry.id},
        )
        await ctx.log(f"{provider}: progress set to chapter {target}")
        pushed += 1

    await ctx.log(f"chapter {chapter} recorded, {pushed} lists updated", pct=100)
