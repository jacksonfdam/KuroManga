"""Recording that reading happened, separately from where it now stands.

Both paths that move progress forward call this: `progress_push`, which derives
a chapter from what Komga says is finished, and `progress_write`, which carries
a number the user stated by hand. Neither of them changes what it pushes
outward — this only writes down that the push happened.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ProgressSource


async def furthest_read(session: AsyncSession, series_id: int) -> int:
    """The series' recorded progress across every list it appears on.

    Read before the entries are updated, because the delta is the distance the
    series moved and afterwards there is nothing left to measure against.

    Every entry counts, including one whose provider has no stored token: the
    question is how far the series has been read, not how far we are able to
    push it.
    """
    result = await session.execute(
        text(
            """
            select coalesce(max(user_progress_chapter), 0)
              from list_entry where series_id = :series_id
            """
        ),
        {"series_id": series_id},
    )
    return int(result.scalar_one())


async def record(
    session: AsyncSession,
    series_id: int,
    *,
    before: int,
    chapter: int,
    source: ProgressSource,
) -> bool:
    """Write one event for a forward movement. Returns whether one was written.

    One row per series, not per list entry: two providers tracking the same
    manga are two records of one act of reading, and a row each would double
    every figure the stats screen draws.
    """
    if chapter <= before:
        return False
    await session.execute(
        text(
            """
            insert into progress_event (series_id, chapter, delta, source, created_at)
            values (:series_id, :chapter, :delta, :source, now())
            """
        ),
        {
            "series_id": series_id,
            "chapter": chapter,
            "delta": chapter - before,
            "source": str(source),
        },
    )
    return True
