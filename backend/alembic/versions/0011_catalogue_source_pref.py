"""site_catalogue and source_pref

Revision ID: 0011_catalogue_source_pref
Revises: 0010_split_prose_from_comic
Create Date: 2026-09-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011_catalogue_source_pref"
down_revision: str | None = "0010_split_prose_from_comic"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Generated output, replaced wholesale on every regeneration - see
    # app/catalogue/repo.py. Keyed on the site key itself rather than a
    # surrogate id: the upsert-by-key that a regeneration needs is simplest
    # when the key is the primary key.
    op.execute(
        """
        create table if not exists site_catalogue (
            key varchar(100) primary key,
            name varchar(200) not null,
            template varchar(50) not null,
            base_url text not null,
            lang varchar(10) not null,
            nsfw boolean not null default false,
            overrides jsonb not null default '{}'::jsonb,
            rate_limit jsonb,
            version text not null,
            hand_ported boolean not null default true
        )
        """
    )
    # No foreign key to site_catalogue, deliberately: a regeneration deletes
    # a vanished site's catalogue row outright (see replace_catalogue), and a
    # foreign key here would cascade that delete onto the user's own
    # preference instead of leaving it behind, orphaned, for the settings
    # screen to say so.
    op.execute(
        """
        create table if not exists source_pref (
            key varchar(100) primary key,
            enabled boolean not null default true,
            priority integer not null default 100,
            rate_limit_override jsonb,
            disabled_reason text
        )
        """
    )


def downgrade() -> None:
    op.execute("drop table if exists source_pref")
    op.execute("drop table if exists site_catalogue")
