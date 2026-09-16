"""remember a series the user removed, so a sync does not bring it back

Revision ID: 0017_removed_entry
Revises: 0016_job_permanent
Create Date: 2026-09-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_removed_entry"
down_revision: str | None = "0016_job_permanent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Deleting a series is not enough on its own. `list_entry` survives the
    # cascade with a null series_id, and `list_sync` matches on it, so the
    # series a user removed would return within six hours - which reads as the
    # remove button not working rather than as a sync doing its job.
    #
    # Keyed by the provider's own id rather than by the series, because the
    # series is exactly what is being deleted and its id would be meaningless
    # a moment later.
    op.create_table(
        "removed_entry",
        sa.Column("provider", sa.String(20), primary_key=True),
        sa.Column("provider_media_id", sa.String(50), primary_key=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("removed_entry")
