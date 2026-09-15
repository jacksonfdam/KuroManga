"""seed the v1 sites

Revision ID: 0013_seed_v1_sites
Revises: 0012_seed_native_sources
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_seed_v1_sites"
down_revision: str | None = "0012_seed_native_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# All five land together although only mangathemesia has a class today. A row
# whose template has no implementation is skipped by registry.reload with a log
# line saying so, which is what lets the catalogue describe more than this
# deployment can currently run.
#
# Seeded by hand rather than generated: the generator (issue #100) replaces the
# template rows wholesale when it arrives, and replace_catalogue already scopes
# its deletes away from native rows so the two hand-written sites survive it.
SITES = [
    ("thunderscans", "Thunder Scans", "mangathemesia", "https://en-thunderscans.com", False),
    ("vortexscans", "Vortex Scans", "iken", "https://vortexscans.org", False),
    ("orionscans", "Orion Scans", "iken", "https://orion-scans.com", False),
    ("mangageko", "MangaGeko", "native", "https://www.mgeko.cc", True),
    ("asurascans", "Asura Scans", "native", "https://asurascans.com", False),
]

CATALOGUE = sa.text(
    """
    insert into site_catalogue
        (key, name, template, base_url, lang, nsfw, overrides, version, hand_ported)
    values (:key, :name, :template, :base_url, 'en', :nsfw, '{}'::jsonb, '1', true)
    on conflict (key) do nothing
    """
)

# Enabled on arrival: these are the sites this library downloads from, and a
# site seeded disabled is one the user has to discover before it does anything.
# Turning it off afterwards is their decision to make.
PREFERENCE = sa.text(
    "insert into source_pref (key, enabled) values (:key, true) on conflict (key) do nothing"
)


def upgrade() -> None:
    bind = op.get_bind()
    for key, name, template, base_url, nsfw in SITES:
        bind.execute(
            CATALOGUE,
            {"key": key, "name": name, "template": template, "base_url": base_url, "nsfw": nsfw},
        )
        bind.execute(PREFERENCE, {"key": key})


def downgrade() -> None:
    bind = op.get_bind()
    keys = [key for key, *_ in SITES]
    bind.execute(sa.text("delete from source_pref where key = any(:keys)"), {"keys": keys})
    bind.execute(sa.text("delete from site_catalogue where key = any(:keys)"), {"keys": keys})
