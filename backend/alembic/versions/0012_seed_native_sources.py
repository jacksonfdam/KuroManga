"""seed mangadex and comick as native catalogue rows, both enabled

Revision ID: 0012_seed_native_sources
Revises: 0011_catalogue_source_pref
Create Date: 2026-09-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012_seed_native_sources"
down_revision: str | None = "0011_catalogue_source_pref"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The registry is built from site_catalogue joined against source_pref
    # (see app/sources/registry.py) - without these two rows an existing
    # database migrates into a registry with nothing in it, and searching and
    # downloading stop for the whole library. mangadex and comick are
    # hand-written Python classes rather than generated template leaves, so
    # they carry template = 'native' and the generator never produces or
    # deletes them (see replace_catalogue's `and template <> 'native'`).
    op.execute(
        """
        insert into site_catalogue
            (key, name, template, base_url, lang, nsfw, overrides, rate_limit,
             version, hand_ported)
        values
            ('mangadex', 'MangaDex', 'native', 'https://mangadex.org', 'en', false,
             '{}'::jsonb, null, '1.0.0', true),
            ('comick', 'WeebCentral', 'native', 'https://weebcentral.com', 'en', false,
             '{}'::jsonb, null, '1.0.0', true)
        on conflict (key) do nothing
        """
    )
    op.execute(
        """
        insert into source_pref (key, enabled)
        values ('mangadex', true), ('comick', true)
        on conflict (key) do nothing
        """
    )


def downgrade() -> None:
    op.execute("delete from source_pref where key in ('mangadex', 'comick')")
    op.execute("delete from site_catalogue where key in ('mangadex', 'comick')")
