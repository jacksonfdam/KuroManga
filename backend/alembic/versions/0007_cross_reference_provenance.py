"""record who asserted each cross reference

Revision ID: 0007_cross_reference_provenance
Revises: 0006_review_ignored
Create Date: 2026-09-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007_cross_reference_provenance"
down_revision: str | None = "0006_review_ignored"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Turn {"mal": "7001"} into {"mal": {"id": "7001", "by": null}}.

    The flat shape recorded the identifier and nothing about where it came from,
    so the provenance of anything already stored is genuinely unknown. It is
    written as null rather than guessed: an assertion of unknown origin is not
    authoritative, which is the conservative reading and the one that cannot
    wrongly outrank a provider speaking about its own database.
    """
    op.execute(
        """
        update series
           set meta = jsonb_set(
                   meta,
                   '{cross_refs}',
                   (
                       select jsonb_object_agg(
                           key,
                           jsonb_build_object('id', value, 'by', null)
                       )
                         from jsonb_each_text(meta -> 'cross_refs')
                   )
               )
         where meta -> 'cross_refs' is not null
           and jsonb_typeof(meta -> 'cross_refs') = 'object'
           and exists (
               select 1
                 from jsonb_each(meta -> 'cross_refs') e
                where jsonb_typeof(e.value) = 'string'
           )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        update series
           set meta = jsonb_set(
                   meta,
                   '{cross_refs}',
                   (
                       select jsonb_object_agg(key, value -> 'id')
                         from jsonb_each(meta -> 'cross_refs')
                   )
               )
         where meta -> 'cross_refs' is not null
           and jsonb_typeof(meta -> 'cross_refs') = 'object'
           and exists (
               select 1
                 from jsonb_each(meta -> 'cross_refs') e
                where jsonb_typeof(e.value) = 'object'
           )
        """
    )
