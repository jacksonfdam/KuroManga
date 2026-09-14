"""when reading progress moved, not only where it is now

Revision ID: 0005_progress_event
Revises: 0004_anime_manga_dismissed
Create Date: 2026-09-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005_progress_event"
down_revision: str | None = "0004_anime_manga_dismissed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # list_entry.user_progress_chapter is a current value that the next sync
    # overwrites, so "chapters read on Tuesday" is unanswerable from it. This
    # table is append-only and fills forward from the day it ships: no backfill
    # is possible, and inventing one would put figures on a chart that nothing
    # measured.
    op.execute(
        """
        create table if not exists progress_event (
            id bigserial primary key,
            series_id bigint not null references series(id) on delete cascade,
            chapter numeric(8, 2) not null,
            delta numeric(8, 2) not null,
            source varchar(20) not null,
            created_at timestamptz not null default now()
        )
        """
    )
    # Every read of this table is a date range over the whole history; none of
    # them start from a series.
    op.execute(
        "create index if not exists ix_progress_event_created_at "
        "on progress_event (created_at)"
    )


def downgrade() -> None:
    op.execute("drop index if exists ix_progress_event_created_at")
    op.execute("drop table if exists progress_event")
