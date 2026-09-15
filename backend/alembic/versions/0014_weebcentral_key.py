"""rename the comick catalogue row to the site it actually serves

Revision ID: 0014_weebcentral_key
Revises: 0013_seed_v1_sites
Create Date: 2026-09-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014_weebcentral_key"
down_revision: str | None = "0013_seed_v1_sites"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Everywhere else, a catalogue key is the source's own site: source_mapping
    # stores 'weebcentral', source_pref is keyed the same, and the handlers look
    # a catalogue row up by the site they are downloading from. This one row was
    # keyed after the service that fetches it rather than the site it serves, so
    # that lookup found nothing and the first real weebcentral download failed
    # with "source weebcentral is no longer in the catalogue".
    #
    # The preference moves with it, or a site somebody had disabled comes back
    # enabled under its new name.
    # The stale row is cleared first. 0012 seeds and deletes its native rows by
    # the old key, so once this rename has run its downgrade leaves the renamed
    # row behind; upgrading again then finds both names present and the rename
    # collides on the primary key. Deleting the target first makes both
    # directions repeatable.
    op.execute("delete from source_pref where key = 'weebcentral'")
    op.execute("delete from site_catalogue where key = 'weebcentral'")
    op.execute("update source_pref set key = 'weebcentral' where key = 'comick'")
    op.execute(
        "update site_catalogue set key = 'weebcentral', name = 'WeebCentral' where key = 'comick'"
    )


def downgrade() -> None:
    op.execute("delete from source_pref where key = 'comick'")
    op.execute("delete from site_catalogue where key = 'comick'")
    op.execute("update source_pref set key = 'comick' where key = 'weebcentral'")
    op.execute("update site_catalogue set key = 'comick', name = 'WeebCentral' where key = 'weebcentral'")
