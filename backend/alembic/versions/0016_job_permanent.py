"""mark a failure that retrying cannot mend

Revision ID: 0016_job_permanent
Revises: 0015_mangafire_site
Create Date: 2026-09-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_job_permanent"
down_revision: str | None = "0015_mangafire_site"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Retry cleared the ladder for any failed job, so the interface offered the
    # button on failures that could never succeed — a progress write to a series
    # no writable list holds, a chapter the source carries in no language we
    # asked for. Pressing it queued work that failed again a second later.
    #
    # Nothing is backfilled. The reason a past job failed is not recoverable
    # from its text, and guessing would mark retryable work permanent; the rows
    # that are already wrong correct themselves by failing once more under the
    # new code.
    op.add_column(
        "job",
        sa.Column("permanent", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("job", "permanent")
