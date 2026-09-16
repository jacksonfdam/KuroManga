"""add mangafire to the catalogue, disabled

Revision ID: 0015_mangafire_site
Revises: 0014_weebcentral_key
Create Date: 2026-09-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015_mangafire_site"
down_revision: str | None = "0014_weebcentral_key"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Content warning MIXED upstream, so nsfw is true: what the site carries is
    # a fact about the site, and what the interface does with it belongs to the
    # settings screen.
    op.execute(
        """
        insert into site_catalogue
            (key, name, template, base_url, lang, nsfw, overrides, rate_limit,
             version, hand_ported)
        values
            ('mangafire', 'MangaFire', 'native', 'https://mangafire.to', 'en', true,
             '{}'::jsonb, '{"permits": 2, "period_seconds": 1}'::jsonb, '1.0.0', true)
        on conflict (key) do nothing
        """
    )
    # No source_pref row, so it is not enabled and not registered. It cannot
    # work until someone clears the site's check in a browser and pastes the
    # cookie into settings, and a source that is on but cannot answer is worse
    # than one the reader turns on deliberately.
    op.execute("delete from source_pref where key = 'mangafire'")


def downgrade() -> None:
    op.execute("delete from source_pref where key = 'mangafire'")
    op.execute("delete from site_catalogue where key = 'mangafire'")
