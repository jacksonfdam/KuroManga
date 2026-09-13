"""per-series auto download flag

Revision ID: 0002_auto_download
Revises: 0001_initial
Create Date: 2026-09-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_auto_download"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Off by default: confirming a source mapping tells the pipeline what a series
    # is, not that its whole backlog should be fetched.
    op.execute(
        "alter table series add column if not exists auto_download boolean not null default false"
    )


def downgrade() -> None:
    op.execute("alter table series drop column if exists auto_download")
