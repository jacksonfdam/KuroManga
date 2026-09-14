"""the wanted relations a parser had to throw away, so Unmatched can explain itself

Revision ID: 0008_anime_discarded_relations
Revises: 0007_progress_event_series_index
Create Date: 2026-09-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008_anime_discarded_relations"
down_revision: str | None = "0007_progress_event_series_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # No default and nullable on purpose: recording only starts on the next
    # anime_list_sync, so NULL has to keep meaning "not recorded yet" and stay
    # distinct from "[]", which means "recorded, and nothing was discarded".
    # A default of '[]' would make every anime that has not re-synced since
    # this shipped look like AniList declared no source at all.
    op.execute("alter table anime_entry add column if not exists discarded_relations jsonb")


def downgrade() -> None:
    op.execute("alter table anime_entry drop column if exists discarded_relations")
