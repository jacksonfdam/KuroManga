"""anime entries and manga suggestions

Revision ID: 0003_discovery
Revises: 0002_auto_download
Create Date: 2026-09-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_discovery"
down_revision: str | None = "0002_auto_download"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        create table if not exists anime_entry (
            id bigserial primary key,
            provider varchar(20) not null,
            provider_media_id varchar(50) not null,
            title_romaji varchar(500),
            title_english varchar(500),
            synonyms jsonb not null default '[]'::jsonb,
            status varchar(20) not null,
            progress_episode integer not null default 0,
            total_episodes integer,
            cover_url text,
            related_manga jsonb not null default '[]'::jsonb,
            raw jsonb not null default '{}'::jsonb,
            updated_at timestamptz not null default now(),
            constraint uq_anime_entry_provider_media unique (provider, provider_media_id)
        )
        """
    )
    op.execute(
        """
        create table if not exists suggestion (
            id bigserial primary key,
            provider varchar(20) not null,
            provider_media_id varchar(50) not null,
            alt_ids jsonb not null default '{}'::jsonb,
            title varchar(500) not null,
            cover_url text,
            total_chapters integer,
            year integer,
            publishing_status varchar(20),
            state varchar(20) not null default 'new',
            rank_score numeric(5, 4) not null default 0,
            series_id bigint references series(id) on delete set null,
            meta jsonb not null default '{}'::jsonb,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now(),
            constraint uq_suggestion_provider_media unique (provider, provider_media_id)
        )
        """
    )
    # The Discovery screen reads one slice, ordered: new suggestions, best first.
    op.execute(
        "create index if not exists ix_suggestion_state_rank on suggestion (state, rank_score desc)"
    )


def downgrade() -> None:
    op.execute("drop index if exists ix_suggestion_state_rank")
    op.execute("drop table if exists suggestion")
    op.execute("drop table if exists anime_entry")
