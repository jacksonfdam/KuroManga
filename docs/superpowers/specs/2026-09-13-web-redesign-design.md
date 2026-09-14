# Web redesign: the six-screen interface from the PRD

Date: 2026-09-13
Status: approved for planning

## Problem

The interface is four hand-styled pages sharing one 4 KB stylesheet. It shows what the
pipeline is doing, and nothing else. It has no visual system, no covers worth looking at, no
way to read a series' own page, no sense of the library as a collection.

The `.redesign/` folder holds a product brief and six high-fidelity screens with a complete
design system behind them. Two of those screens have no code behind them at all: Discovery,
which turns a finished anime into a manga suggestion, and Stats, which reports on reading.
The other four exist but look nothing like the design.

This document covers both halves at once — the visual system and the data the screens need —
because a screen designed against data the API does not serve is a mockup, not an interface.

## Scope

In:

- A design token layer and component primitives taken from `.redesign/obsidian_vault/DESIGN.md`.
- An application shell: header, navigation with live badges, integration status strip.
- Six screens: Home, Library, Discovery, Series detail, Stats, Settings.
- The API surface each screen needs, including the Discovery subsystem described in
  `2026-09-13-anime-manga-discovery-design.md`.
- MangaDex promoted from a chapter source to a list write destination.

Out:

- Mobile applications. The interface is responsive down to 640 px; Komga's own apps remain
  the way to read on a phone.
- Multi-user accounts. This is one person's homelab. The avatar in the mockups is decoration,
  not a session.
- Any reading view. Komga reads; KuroManga acquires and tracks.

## The design system

### Where the tokens come from

`DESIGN.md` carries two colour definitions that disagree. Its front matter names a Material 3
token map with `primary: #d0bcff` over a `#10141a` canvas. Its prose names "Primary Violet
`#8b5cf6`" over `#0d1117`. The six mockups all embed the front matter map in their inline
`tailwind.config`, and the screenshots were rendered from it.

The front matter wins: it is what was actually built and reviewed. The prose is kept for the
one thing the token map lacks — the semantic status palette — which is mapped onto the
Material 3 roles rather than carried as a second, competing set of hexes.

### Status colours

| Reading status | Role | Value |
|---|---|---|
| Reading | `secondary` | `#4edea3` |
| Completed | `primary` | `#d0bcff` |
| Plan to read | `tertiary` | `#7bd0ff` |
| On hold | `warning` (new token) | `#ffb877` |
| Dropped | `error` | `#ffb4ab` |

`warning` is the one token added beyond the Material 3 set, because a five-state list cannot
be expressed in four roles without overloading one of them.

### Build

Tailwind becomes a real dependency with a PostCSS step, not the CDN script the mockups load.
The token map lives in `tailwind.config.ts` as the single source; nothing hardcodes a hex.

Plus Jakarta Sans and JetBrains Mono are self-hosted through `@fontsource`, and Material
Symbols are replaced by inline SVG icons. Both for the same reason: this runs on a homelab
box that may have no route to the public internet, and an interface that loses its typography
and every icon when the WAN is down is not a self-hosted interface.

### Primitives

`frontend/src/ui/` holds the pieces every screen shares, each one presentational and taking
its data as props:

`Button`, `IconButton`, `Badge`, `StatusPill`, `Chip` (with count slot), `Card`, `Toggle`,
`SegmentedControl`, `ProgressBar`, `Icon`, `Skeleton`, `EmptyState`.

Two are specific enough to name their behaviour:

- **`CoverCard`** — 2:3 cover, hairline border, progress track docked flush to the bottom
  edge, hover lift of 4 px with a violet rim glow. Badges overlay the art; the title sits
  below it, never on it, so a long romanised title cannot cover the art it describes.
- **`QuickIncrement`** — the `+1 Ch` control. Glass background, optimistic update with an
  emerald flash, and a rollback when the write fails. It never blocks on the network: the
  whole point of the control is that reading a chapter costs one click.

### File layout

```
frontend/src/
  app/         AppShell.tsx, routes.tsx
  ui/          the primitives above
  features/
    home/      dashboard
    library/   grid, table, filters, continue-reading
    discovery/ suggestion cards, approval
    series/    detail page
    downloads/ queue and job events
    review/    candidate confirmation
    stats/     charts
    settings/  integration and pipeline configuration
  lib/         api.ts, useEvents.ts, format.ts
  styles/      index.css
```

One folder per screen, primitives shared, no cross-imports between features. A feature folder
that needs something from another feature is a signal that the thing belongs in `ui/`.

## What each screen needs

### Home

A pipeline status line, four metric cards, a continue-reading strip, and a two-column split
of Discovery highlights against the live job stream.

Served by one new endpoint, `GET /api/dashboard`, because six parallel requests to build one
above-the-fold view is the kind of thing that looks fine on localhost and falls apart on a
NAS. It returns queue counts, worker state, next cron fire times, the continue-reading set,
the top suggestions, and storage figures.

Storage comes from `shutil.disk_usage` on the library path. The mockup's "1.84 TB / 4.0 TB
(ZFS Pool)" is a filesystem question, not a ZFS one, and asking the kernel keeps it true on
ext4 too.

### Library

The screen the PRD leans on hardest, and the one closest to already working.

`list_entry.status` and `list_entry.user_progress_chapter` already exist and are already
synced. What is missing is exposure: `GET /api/series` does not return either. Adding them
turns on the status tabs, the progress bars and the continue-reading strip at once.

Score, genre and format are not columns, but `list_entry.raw` holds the provider payload they
came in. They are read out of it at query time rather than denormalised into new columns,
because a new column is a new thing to keep in sync and these three are display-only.

Grid and table are two renderings of one fetched list, not two endpoints. The table's inline
edit writes through the same progress endpoint the `+1 Ch` button uses.

### Discovery

Built on `2026-09-13-anime-manga-discovery-design.md`, which is approved and unimplemented.
This redesign implements it. The screen shows suggestion cards carrying the reason the
suggestion exists — which anime, how far its adaptation reached, how much manga remains —
and approves with a chosen status in one click.

### Series detail

A route that does not exist today. Cover and metadata, the mapping and which source it
resolves to, the chapter table with local file state, the sync targets and their last write,
and the per-series controls: auto-download, download a range, re-run the search.

Served by `GET /api/series/{id}`, assembling what `/chapters`, `/candidates` and the series
row already hold.

### Stats

The screen with a genuine data gap.

Nothing in the schema records *when* reading progress changed. `user_progress_chapter` is a
current value with no history, so "chapters read per day over the last 30 days" cannot be
computed from what exists. A new `progress_event` table records each forward movement, written
by `progress_push` and by the manual increment path.

This fills forward only. The velocity chart is empty the day it ships and becomes useful over
the following weeks, and the screen says so rather than showing a flat line as though nothing
had been read.

"Time spent" has no source at all. It is derived as chapters read times a configurable
`reading_minutes_per_chapter`, and labelled an estimate in the interface. A number presented
as measured when it was assumed is worse than no number.

Everything else on the screen — status distribution, top genres, publication eras, totals —
is an aggregate over `list_entry` and `chapter`, available now.

### Settings

Mostly restyling. The keys the mockup exposes largely exist already: `cron_list_sync`,
`cron_chapter_discover`, `cron_progress_push`, `download_concurrency`,
`per_source_concurrency`, `download_batch_size`, `auto_download_new`.

New keys: `cron_anime_sync`, `comick_url`, `comick_enabled`, `reading_minutes_per_chapter`.

The integration strip in the header is served by `GET /api/health/integrations`, which reports
each of MAL, AniList, MangaDex, Komga and Comick as reachable, authenticated, or neither,
plus AniList's rate-limit headroom.

## API additions

| Endpoint | Purpose |
|---|---|
| `GET /api/series` *(extended)* | adds status, progress, score, genre, format, last activity |
| `GET /api/series/{id}` | detail page payload |
| `POST /api/series/{id}/progress` | set read chapter; forward-only |
| `GET /api/dashboard` | Home in one request |
| `GET /api/stats?period=` | Stats aggregates |
| `GET /api/health/integrations` | header status strip |
| `GET /api/suggestions` | Discovery list |
| `POST /api/suggestions/{id}/approve` | quad-destination write |
| `POST /api/suggestions/{id}/dismiss` | permanent refusal |

## Data model additions

Beyond `anime_entry` and `suggestion` from the discovery design:

```sql
CREATE TABLE progress_event (
    id BIGSERIAL PRIMARY KEY,
    series_id BIGINT NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    chapter NUMERIC(8,2) NOT NULL,
    delta NUMERIC(8,2) NOT NULL,
    source VARCHAR(20) NOT NULL, -- komga | manual
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_progress_event_time ON progress_event (created_at);
```

## The golden rule and the manual increment

The PRD is explicit that `LIST_WRITE` changes status and never progress, and that progress
belongs to `progress_push`. A `+1 Ch` click in the interface is a third path and must not
break that rule by smuggling progress into a status write.

It gets its own job type, `PROGRESS_WRITE`, carrying an explicit chapter number. It shares
`progress_push`'s forward-only guard: a write that would lower a provider's recorded progress
is dropped, not sent. Marking a series complete still cannot zero a counter.

## The provider interface grows

`ListSource` in `providers/base.py` today declares `fetch_list`, `push_progress` and the OAuth
pair. Discovery and the quad-destination write need three things it does not have:

- `fetch_anime_list` — the anime side of the same account, with the relation edges that name
  which manga an anime adapts.
- `push_status` — set a list entry's status without touching its progress. The golden rule
  above is easier to keep when the interface itself cannot express the violation.
- `add_to_list` — create the entry approval needs, where `push_status` assumes one exists.

`fetch_anime_list` is optional with a default returning nothing: a list provider that has no
anime side is not broken, it simply contributes no suggestions.

`Provider` gains `MANGADEX`, implemented as a `ListSource` in `providers/mangadex.py`. That
file sits beside an existing and unrelated `sources/mangadex.py`, which is the chapter source.
The two are different services on the same host and must not be merged: one reads a reading
list over OAuth, the other resolves chapters. The parallel filenames are a hazard worth a
comment in both.

## Testing

The existing boundaries make this straightforward: `providers/`, `sources/`, `downloader/`
and `komga/` stay pure and keep being tested from recorded fixtures.

- New handlers (`ANIME_LIST_SYNC`, `SUGGEST_BUILD`, `LIST_WRITE`, `PROGRESS_WRITE`) get
  handler tests against the throwaway Postgres, as the existing ones do.
- New endpoints get API tests, including the forward-only guard on progress, which is the one
  place a bug silently destroys data on a remote service.
- Aggregation queries get tests with seeded rows, because an off-by-one in a date bucket is
  invisible by inspection.
- The frontend gets `tsc -b` and a build in CI. Component tests are not proposed: the
  components are presentational and the behaviour worth testing lives in the API.

## Decomposition

Eleven issues. 1-2 and 8 are independent; the rest chain.

| # | Issue | Area | Depends on |
|---|---|---|---|
| 1 | Tailwind, design tokens, self-hosted fonts, SVG icons | web | — |
| 2 | App shell: header, navigation, badges, integration strip | web | 1 |
| 3 | Extend `/api/series`; progress endpoint and `PROGRESS_WRITE` | api | — |
| 4 | Library: grid and table, status tabs, continue-reading, `+1 Ch` | web | 2, 3 |
| 5 | Review and Downloads redesign | web | 2 |
| 6 | Settings redesign and new keys | web | 2 |
| 7 | Series detail route and endpoint | web | 2, 3 |
| 8 | Discovery backend: `anime_entry`, `suggestion`, sync and build jobs | providers | — |
| 9 | MangaDex as a list provider; quad-destination approval | providers | 8 |
| 10 | Discovery screen | web | 2, 9 |
| 11 | Home and Stats: `progress_event`, aggregates, both screens | api | 4, 10 |

## Acceptance criteria

1. No hex colour, font size or spacing value appears outside `tailwind.config.ts`.
2. The interface renders completely with no outbound internet route: fonts and icons load
   from the bundle.
3. Every string in the interface is English.
4. The library status tabs and progress bars are driven by `list_entry`, not by placeholder
   data. No screen ships a widget whose number is invented.
5. `+1 Ch` updates the card immediately and reconciles against the server; a rejected write
   restores the previous value visibly.
6. A progress write that would move a provider backwards is not sent.
7. Approving a suggestion writes to MyAnimeList, AniList and MangaDex and creates the Komga
   folder; a failure in one destination retries only that destination.
8. A dismissed suggestion never appears again.
9. The Stats velocity chart states that it measures from the day `progress_event` began, and
   "time spent" is labelled an estimate.
10. Every screen is usable at 640 px with no horizontal scroll outside tables and charts.
