"""index for the per-series reading frequency query

Revision ID: 0007_progress_event_series_index
Revises: 0006_review_ignored
Create Date: 2026-09-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007_progress_event_series_index"
down_revision: str | None = "0006_review_ignored"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # progress_event only had ix_progress_event_created_at, built for the Stats
    # screen's whole-history scan. The series detail page filters on series_id
    # first and then a date range, and that shape has had no index to use since
    # this table shipped - fine while the table is nearly empty, not once every
    # detail page load runs this query against real history.
    op.execute(
        "create index if not exists ix_progress_event_series_created "
        "on progress_event (series_id, created_at)"
    )


def downgrade() -> None:
    op.execute("drop index if exists ix_progress_event_series_created")
