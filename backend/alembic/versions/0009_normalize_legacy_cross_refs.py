"""give the cross references still stored as bare strings a provenance

Revision ID: 0009_normalize_legacy_cross_refs
Revises: 0008_anime_discarded_relations
Create Date: 2026-09-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009_normalize_legacy_cross_refs"
down_revision: str | None = "0008_anime_discarded_relations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Turn {"mal": "7001"} into {"mal": {"id": "7001", "by": null}}.

    0007_cross_reference_provenance carried this conversion, but it was written
    in parallel with 0007_progress_event_series_index and re-parented underneath
    it afterwards. A database that had already recorded the index revision was
    therefore at head with the conversion never run, and the reader landed on
    data still in the old shape. Repeating the conversion under a new revision is
    what reaches those databases; it is a no-op on any database the earlier one
    did run against.

    Authorship is written as null rather than reconstructed. The old writer put a
    provider's own identifier and its quotes of other providers into the same
    flat map with no record of which was which, so who stated any given entry is
    genuinely unrecoverable. An assertion of unknown origin is not authoritative,
    so a provider speaking firsthand about its own database replaces it - which a
    guess, being indistinguishable from a real attribution, would prevent.
    """
    op.execute(
        """
        update series
           set meta = jsonb_set(
                   meta,
                   '{cross_refs}',
                   (
                       select jsonb_object_agg(
                           e.key,
                           case
                               when jsonb_typeof(e.value) = 'string'
                               then jsonb_build_object('id', e.value, 'by', null)
                               else e.value
                           end
                       )
                         from jsonb_each(meta -> 'cross_refs') e
                   )
               )
         where jsonb_typeof(meta -> 'cross_refs') = 'object'
           and exists (
               select 1
                 from jsonb_each(meta -> 'cross_refs') e
                where jsonb_typeof(e.value) = 'string'
           )
        """
    )


def downgrade() -> None:
    """Flatten each assertion back to the identifier it carries.

    Whoever stated it is dropped, because the old shape has nowhere to put it.
    """
    op.execute(
        """
        update series
           set meta = jsonb_set(
                   meta,
                   '{cross_refs}',
                   (
                       select jsonb_object_agg(
                           e.key,
                           case
                               when jsonb_typeof(e.value) = 'object'
                               then coalesce(e.value -> 'id', 'null'::jsonb)
                               else e.value
                           end
                       )
                         from jsonb_each(meta -> 'cross_refs') e
                   )
               )
         where jsonb_typeof(meta -> 'cross_refs') = 'object'
           and exists (
               select 1
                 from jsonb_each(meta -> 'cross_refs') e
                where jsonb_typeof(e.value) = 'object'
           )
        """
    )
