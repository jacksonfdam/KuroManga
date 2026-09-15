# Data model

Source of truth: `backend/app/models.py` and `backend/alembic/versions/`. Twelve tables. The
enumerations live in `backend/app/enums.py` and are stored as strings, not as Postgres enum types,
so adding a member needs no migration.

## The central idea

**A list entry is not a series.** `list_entry` is one row per provider — the same manga on
MyAnimeList and on AniList is two rows. `series` is the canonical work those rows point at.

That separation is what makes one mapping, one folder and one download serve however many lists a
title appears on. Almost every subtlety in `list_sync` exists to decide, correctly, which `series` a
`list_entry` belongs to.

## Reading and downloading

### `series`
The canonical work.

`id`, `canonical_title`, `slug` (unique; the folder name), `komga_series_id`, `needs_review`,
`auto_download`, `review_ignored_at`, `meta` (jsonb), `created_at`

- **`slug` is the folder name** and is reserved uniquely at creation — colliding titles get a numeric
  suffix.
- **`auto_download` is opt-in and defaults false.** Only a followed series has its missing chapters
  queued by discovery. Confirming a mapping does not imply fetching a backlog; before this existed,
  forty-five confirmations queued tens of thousands of chapters.
- **`meta.aliases`** holds normalised titles, widened as each provider contributes spellings.
- **`meta.cross_refs`** holds identifiers with their provenance. See
  [`providers.md`](providers.md#identity-and-hearsay).

### `list_entry`
One row per provider per work. Unique on `(provider, provider_media_id)`.

`id`, `provider`, `provider_media_id`, `series_id`, `title_romaji`, `title_english`, `synonyms`,
`status`, `user_progress_chapter`, `total_chapters`, `cover_url`, `raw` (jsonb), `updated_at`

`raw` keeps the provider's own payload. Metadata for `ComicInfo.xml` is read out of it at use time
rather than denormalised into columns — a column is another thing to keep in sync, and these are
display-only.

### `source_mapping`
The confirmed link from a series to a source URL. `active` is false for superseded mappings rather
than deleting history.

### `site_catalogue`
Every source site the pipeline knows how to reach, and how to reach it.

`key` (primary key), `name`, `template`, `base_url`, `lang`, `nsfw`, `overrides` (jsonb),
`rate_limit` (jsonb), `version`, `hand_ported`

Generated output. `app/catalogue/repo.py::replace_catalogue` is the only thing that writes it: it
upserts every row a regeneration produced and deletes the keys that run left out. Two exceptions are
deliberate. Rows with `template = 'native'` are never deleted — MangaDex and comick are hand-written
Python classes, and the generator parses an extension repository that mentions neither. And an empty
regeneration is refused rather than applied, because the source registry is built from this table
and an accepted empty run would disable searching and downloading for the whole library at once.

`hand_ported` is false for a site whose extension carries behaviour the generator cannot derive. It
ships in the catalogue but disabled, with the reason on its settings row.

### `source_pref`
The user's own decision about a site, kept in a separate table on purpose.

`key` (primary key), `enabled`, `priority`, `rate_limit_override` (jsonb), `disabled_reason`

A regenerated catalogue must never silently re-enable a site someone turned off, or forget one they
turned on, so nothing that writes the catalogue touches this table. A preference whose site vanished
upstream is kept and shown as orphaned rather than deleted. There is no foreign key between the two
tables for the same reason: one would cascade the catalogue's delete straight onto the preference.

`source_mapping.source_site` likewise stays a plain string against the catalogue key, with no
foreign key. A confirmed mapping outlives a regeneration, and if its site is gone the download fails
naming the site — more use than the mapping quietly disappearing.

The registry every source lookup goes through is these two tables joined: loaded once at boot in
both the API and the worker, so enabling a site in settings is the same act as registering it.

### `series_candidate`
Search results awaiting confirmation. Replaced wholesale on each `match_search`.

### `chapter`
What exists and what is held locally. Unique on `(series_id, number)`.

`id`, `series_id`, `number` (`Numeric`), `title`, `source_url`, `state`, `file_path`,
`komga_book_id`, `discovered_at`

**`state` is the record of what is missing**, reconciled against Komga rather than the filesystem, so
moving files by hand does not cause a redownload.

`known` → `queued` → `downloading` → `downloaded`, with `failed` and `skipped` as ends. `skipped`
means the source will not serve it in the requested language; it does not return to retry.

`number` is `Numeric`, not an integer — half chapters are real and `12.5` must survive.

## The queue

### `job`
`id`, `type`, `payload` (jsonb), `state`, `priority`, `attempts`, `max_attempts`, `lease_until`,
`run_after`, `last_error`, `dedupe_key`, `series_id`, `created_at`, `started_at`, `finished_at`

Indexes that matter: `(state, priority, created_at)` for the lease, `(state, lease_until)` for
reclaiming, and a **partial unique index on `(type, dedupe_key)` restricted to `pending` and
`leased`** — which is what lets a finished job not block an identical later one.

`priority` ascends: 0 before 100. See [`jobs.md`](jobs.md).

### `job_event`
Append-only progress. `job_id`, `ts`, `level`, `message`, `pct`. This is the operational log the
interface shows; container stdout is for when a container will not start.

## Accounts and configuration

### `provider_token`
One row per provider, keyed by `provider`. `access_token`, `refresh_token`, `expires_at`,
`account_name`.

Only OAuth providers appear here. A provider authenticating with a configured key has nothing stored
— `static_credential()` answers before this table is consulted.

### `setting`
Key/value strings for what the interface may change: concurrency, batch size, cron expressions.
Credentials live in the environment, never here.

## Discovery

### `anime_entry`
The anime mirror. Unique on `(provider, provider_media_id)`.

`related_manga` holds the relation edges naming which manga an anime adapts. `manga_dismissed_at`
makes a dismissal stick so the same title never returns as a suggestion.

### `suggestion`
A manga proposed from an anime. `alt_ids`, `rank_score`, `state`, `series_id` once approved, and
`meta` carrying the reason it exists — which anime, how far the adaptation got, how much manga
remains.

The reason is the point. A suggestion without it is a title the user has to go and research, which
is the work the feature exists to remove.

## History

### `progress_event`
`series_id`, `chapter`, `delta`, `source`, `created_at`.

Written by `progress_push` and by the manual increment path. It exists because
`user_progress_chapter` is a current value with no history, so chapters-per-day cannot be computed
from it.

**It fills forward only.** The velocity chart is empty the day it ships and becomes useful over the
following weeks, and the screen must say so rather than draw a flat line that reads as a month of
reading nothing.

## Migrations

Alembic, in `backend/alembic/versions/`, chained linearly. The `api` container runs
`alembic upgrade head` on start; the test suite migrates from a session fixture in
`tests/conftest.py`.

**Two branches must not both add a migration from the same parent.** That produces two heads and an
upgrade that refuses to run.

**A worktree needs its own database.** Two branches sharing one means whichever migrated last decides
the schema, and a schema ahead of the branch under test makes the suite lie about that branch. Start
a second container on another port and pass `POSTGRES_PORT`.

A shared development database stamped by a branch migration produces
`Can't locate revision identified by ...` on a branch that does not contain it. The database is
wrong, not the branch.
