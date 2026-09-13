"""anime the user says has no manga worth offering

Revision ID: 0004_anime_manga_dismissed
Revises: 0003_discovery
Create Date: 2026-09-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_anime_manga_dismissed"
down_revision: str | None = "0003_discovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Permanent, like dismissing a suggestion: the anime list is re-synced on a
    # schedule and its upsert must not be able to hand back an answer the user
    # already gave. A column on the mirrored row is what survives that.
    op.execute("alter table anime_entry add column if not exists manga_dismissed_at timestamptz")


def downgrade() -> None:
    op.execute("alter table anime_entry drop column if exists manga_dismissed_at")
