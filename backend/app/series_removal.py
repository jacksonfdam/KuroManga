"""Removing a series, and remembering that it was removed.

The first destructive operation in this pipeline, and the reason it needs more
than a delete: `list_entry` survives the cascade with a null series_id and
`list_sync` matches on it, so a series removed at noon returns by six. A
tombstone keyed by the provider's own id is what makes the removal stick.

Downloaded archives are deliberately left on disk. Nothing else here deletes a
file, and a reader who removes a series from the pipeline has not asked to lose
the chapters they already have.
"""

from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def remove_series(session: AsyncSession, series_ids: Sequence[int]) -> int:
    """Remove these series for good. Returns how many rows went.

    One statement per step rather than per series: removing a selection of
    twenty is one decision the user made once, not twenty round trips.
    """
    if not series_ids:
        return 0

    ids = list(series_ids)

    # Recorded before anything is deleted, because the entries are about to go
    # and they are the only place the provider's id for this work is written.
    await session.execute(
        text(
            """
            insert into removed_entry (provider, provider_media_id)
            select provider, provider_media_id
              from list_entry
             where series_id = any(cast(:ids as bigint[]))
            on conflict do nothing
            """
        ),
        {"ids": ids},
    )

    # The entries go too. Left behind they would be orphans with a null series,
    # and the tombstone already carries what a later sync needs to know.
    await session.execute(
        text("delete from list_entry where series_id = any(cast(:ids as bigint[]))"),
        {"ids": ids},
    )

    result = await session.execute(
        text("delete from series where id = any(cast(:ids as bigint[])) returning id"),
        {"ids": ids},
    )
    return len(result.fetchall())
