"""split light novel entries off the manga they were wrongly merged onto

Revision ID: 0010_split_prose_from_comic
Revises: 0009_normalize_legacy_cross_refs
Create Date: 2026-09-15
"""

import json
from collections.abc import Sequence

from sqlalchemy import text

from alembic import op
from app.handlers.list_sync import entry_kind_from_raw, normalize_assertions
from app.providers.base import MANGA_FORMATS, PROSE_FORMATS
from app.text_utils import normalize, slugify

revision: str = "0010_split_prose_from_comic"
down_revision: str | None = "0009_normalize_legacy_cross_refs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _reserve_slug(bind, title: str) -> str:
    """A synchronous copy of app.handlers.list_sync.reserve_slug.

    A migration body cannot await the original, and standing up an event loop
    here just to call one coroutine would be more moving parts than the query
    itself.
    """
    base = slugify(title)
    rows = bind.execute(
        text("select slug from series where slug = :base or slug like :prefix"),
        {"base": base, "prefix": f"{base}-%"},
    ).all()
    taken = {row[0] for row in rows}
    if base not in taken:
        return base
    suffix = 2
    while f"{base}-{suffix}" in taken:
        suffix += 1
    return f"{base}-{suffix}"


def upgrade() -> None:
    """Split every series #116's guard was too late to stop, and repoint the
    cross reference that would otherwise pull the prose entry straight back.

    Detection reuses `entry_kind_from_raw` rather than a second copy of the
    per-provider kind vocabulary (MAL's media_type, AniList's format,
    MangaBaka's Series.type): that mapping is exactly what decides the
    prose/comic boundary at sync time, and a repair judging the boundary by
    its own rules could split a series the guard would not have merged, or
    spare one the guard would now refuse.

    A series is affected when one provider names more than one entry in it
    and those entries land on opposite sides of the boundary - the shape
    issue #88 measured against the live database: a duplicated MangaBaka or
    MyAnimeList entry, one manga, one novel, sharing a series. Once a series
    is judged affected, every entry in it with a prose kind moves out,
    including a lone entry from a provider that was never itself duplicated
    (Mushoku Tensei's AniList entry, for one) - a comic series has no
    legitimate reason to hold a real prose entry, whichever provider said so.
    """
    bind = op.get_bind()

    rows = (
        bind.execute(
            text(
                """
                select id, series_id, provider, provider_media_id, title_romaji,
                       title_english, synonyms, cover_url, raw
                  from list_entry
                 where series_id is not null
                 order by series_id, id
                """
            )
        )
        .mappings()
        .all()
    )

    by_series: dict[int, list] = {}
    for row in rows:
        by_series.setdefault(row["series_id"], []).append(row)

    for series_id, entries in by_series.items():
        kinds = {row["id"]: entry_kind_from_raw(row["provider"], row["raw"]) for row in entries}

        by_provider: dict[str, list] = {}
        for row in entries:
            by_provider.setdefault(row["provider"], []).append(row)

        affected = any(
            {kinds[r["id"]] for r in group} & PROSE_FORMATS
            and {kinds[r["id"]] for r in group} & MANGA_FORMATS
            for group in by_provider.values()
            if len(group) > 1
        )
        if not affected:
            continue

        prose_rows = [r for r in entries if kinds[r["id"]] in PROSE_FORMATS]
        if not prose_rows:
            continue

        titles: list[str] = []
        for row in prose_rows:
            for candidate in (row["title_romaji"], row["title_english"], *(row["synonyms"] or [])):
                if candidate and candidate not in titles:
                    titles.append(candidate)

        canonical_title = next(
            (
                row["title_english"] or row["title_romaji"]
                for row in prose_rows
                if row["title_english"] or row["title_romaji"]
            ),
            f"Unnamed prose split from series {series_id}",
        )
        aliases = sorted({normalize(t) for t in titles if normalize(t)})
        cover_url = next((row["cover_url"] for row in prose_rows if row["cover_url"]), None)
        prose_cross_refs = {
            row["provider"]: {"id": row["provider_media_id"], "by": row["provider"]}
            for row in prose_rows
        }

        slug = _reserve_slug(bind, canonical_title)
        new_series_id = bind.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta, created_at)
                values (:title, :slug, true, cast(:meta as jsonb), now())
                returning id
                """
            ),
            {
                "title": canonical_title,
                "slug": slug,
                "meta": json.dumps(
                    {
                        "titles": titles,
                        "aliases": aliases,
                        "cover_url": cover_url,
                        "cross_refs": prose_cross_refs,
                    }
                ),
            },
        ).scalar_one()

        bind.execute(
            text(
                "update list_entry set series_id = :new_id"
                " where id = any(cast(:ids as bigint[]))"
            ),
            {"new_id": new_series_id, "ids": [r["id"] for r in prose_rows]},
        )

        # The half that makes the split stick. resolve_series checks
        # find_series_by_cross_reference before find_series_by_alias, and the
        # kind guard lives only in the alias path - so a cross_refs entry
        # still naming a prose entry's id lets the very next sync look that id
        # up, find this series still claiming it, and re-merge it right back,
        # silently, because the lookup that finds it never reaches the guard.
        moved = {(r["provider"], r["provider_media_id"]) for r in prose_rows}
        comic_media_id: dict[str, str] = {}
        for row in entries:
            if kinds[row["id"]] not in PROSE_FORMATS and row["provider"] not in comic_media_id:
                comic_media_id[row["provider"]] = row["provider_media_id"]

        held = bind.execute(
            text("select coalesce(meta -> 'cross_refs', '{}'::jsonb) from series where id = :id"),
            {"id": series_id},
        ).scalar_one()

        normalized = normalize_assertions(held or {})
        repointed = dict(normalized)
        changed = False
        for provider, assertion in normalized.items():
            if (provider, assertion.get("id")) not in moved:
                continue
            changed = True
            if provider in comic_media_id:
                repointed[provider] = {**assertion, "id": comic_media_id[provider]}
            else:
                # The comic side has no id of its own for this provider, so
                # there is nothing left to point at; a dangling id is worse
                # than no assertion at all.
                del repointed[provider]

        if changed:
            bind.execute(
                text(
                    """
                    update series
                       set meta = jsonb_set(meta, '{cross_refs}', cast(:refs as jsonb))
                     where id = :id
                    """
                ),
                {"id": series_id, "refs": json.dumps(repointed)},
            )


def downgrade() -> None:
    """Cannot restore a merge, so this does not pretend to.

    The fact that a prose entry and a comic entry once shared a row is exactly
    what the original bug erased the moment they merged; splitting them here
    does not recover it, it only stops it from compounding. Undoing the split
    would need an answer to "which comic series did this used to belong to"
    that exists nowhere - not in this migration, not in the data. So this is
    deliberately empty: the alembic version pointer moves back, and the
    corrected data stays corrected.
    """
