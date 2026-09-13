# Manga download pipeline with MyAnimeList/AniList sync and a Komga library

Date: 2026-09-13
Status: implemented. The README records what has been exercised against live services.

## Problem

The reading lists live on MyAnimeList and AniList. The files need to live in a Komga library, which
already solves reading on web and mobile. Between those two ends there is nothing: the lists give
titles, and `manga-downloader` (github.com/elboletaire/manga-downloader) requires the URL of a source
site. What is missing is the layer that resolves a title to a URL, decides what has not been
downloaded yet, runs downloads in parallel with failure handling, and delivers the files in the
format and layout Komga understands.

The system must also accept CBZ files the user already owns, dropped straight into the library
volume: Komga indexes them the same way, and the pipeline does not overwrite them.

## Scope

In:

- Reading the manga lists on MyAnimeList and AniList.
- A user-confirmed mapping between a list entry and a source site URL.
- Chapter discovery and the delta against what the library already holds.
- Parallel downloads with a persistent queue, retry with backoff, and live progress.
- CBZ generation with a populated `ComicInfo.xml`.
- Creating and scanning the Komga library through its API.
- Writing Komga reading progress back to both lists.
- A four-screen web interface and the complete infrastructure in `docker-compose`.

Out:

- A reader of our own. Komga delivers reading on web and mobile.
- Authentication on the management interface. Local network only.
- Anime lists. Manga only.
- Formats other than CBZ.

## Decisions

| Decision | Choice | Reason |
|---|---|---|
| Title to URL resolution | Manual confirmation in the interface, the pair persisted | No wrong downloads; costs one click per new series |
| List providers | MyAnimeList and AniList in v1 | Both in use; adapters behind a common interface |
| Download triggers | Delta cron, manual button, automatic sync of new entries | Covers daily use, backfill and reprocessing |
| Queue and progress | Postgres only | Already required for the domain and history; `SKIP LOCKED` is enough |
| Komga integration | Shared volume, scan through the API, `ComicInfo.xml`, progress written back, Komga as the truth about what exists | A complete library with no manual work |
| Stack | Python (FastAPI, SQLAlchemy, asyncio) and React (Vite) | Best ecosystem for scraping, metadata and OAuth |
| Architecture | One image, separate processes: `api` and `worker` | `api` restarts without killing a download; `worker` scales |
| Deployment | Homelab on the local network, no authentication, amd64 | Simplicity; adding Tailscale later changes nothing |

`manga-downloader` is invoked as a subprocess of the Go binary, not imported as a library. The worker
reads its stdout line by line and turns it into progress events.

## Data model

The central idea is the separation between a *list entry* and a *canonical series*. Two entries, one
from MyAnimeList and one from AniList, point at the same `series`: one mapping confirmation, one
folder on disk, one download.

```
list_entry   (provider, provider_media_id, title_romaji, title_english, synonyms jsonb,
              status, user_progress_chapter, total_chapters, raw jsonb, updated_at)
   └─ series_id ──> series  (canonical_title, slug, komga_series_id, needs_review,
                             auto_download, metadata jsonb, created_at)
                       ├──> source_mapping  (source_site, source_url, confirmed_at, active)
                       └──> chapter  (number numeric, title, source_url, state,
                                      file_path, komga_book_id, discovered_at)

job        (type, payload jsonb, state, priority, attempts, max_attempts,
            lease_until, last_error, series_id, created_at, started_at, finished_at)
job_event  (job_id, ts, level, message, pct)
provider_token (provider, access_token, refresh_token, expires_at)
setting    (key, value)
series_candidate (series_id, source_site, source_url, title, cover_url,
                  chapter_count, year, score)
```

Enumerations:

- `list_entry.status`: `reading`, `plan_to_read`, `completed`, `on_hold`, `dropped`
- `chapter.state`: `known`, `queued`, `downloading`, `downloaded`, `failed`, `skipped`
  (`skipped` is a chapter the source does not publish in the requested language; it does not go back
  into retry)
- `job.state`: `pending`, `leased`, `done`, `failed`
- `job.type`: `list_sync`, `match_search`, `chapter_discover`, `download_batch`,
  `download_chapter`, `komga_scan`, `progress_push`

`chapter.state` is the record of what is still missing, and it is reconciled against Komga's books
rather than against the disk. Moving files around outside the pipeline therefore does not cause a
redownload.

Required indexes: `job (state, priority, created_at)` for leasing; `job (state, lease_until)` for
recovering an expired lease; `chapter (series_id, number)` unique;
`list_entry (provider, provider_media_id)` unique; `job_event (job_id, ts)`.

## Modules

Each module has one contract and one dependency. The four edges are pure: they take arguments, return
values, and never touch the database. Only `handlers/` writes.

| Module | Responsibility | Does not know about |
|---|---|---|
| `providers/` | `base.py` defines `ListSource`; `mal.py` and `anilist.py` implement `fetch_list()` and `push_progress()`, returning DTOs | Postgres |
| `sources/` | `search(title, synonyms) -> [Candidate]`, `list_chapters(url) -> [ChapterRef]` | The queue, Komga |
| `downloader/` | The binary subprocess, stdout parsing, writing CBZ, injecting `ComicInfo.xml` | Where the request came from |
| `komga/` | `ensure_library()`, `scan_library()`, `books_of(series)`, `read_progress()` | The domain |
| `queue/` | `enqueue`, `lease`, `complete`, `fail`, `notify` | Job types |
| `handlers/` | One handler per job type; stitches the modules above together | HTTP |
| `api/` | FastAPI routes and SSE | Business rules |

## Flow

Each handler enqueues the next one. The pipeline is a chain, not a central orchestrator.

```
cron 6h ──> list_sync(provider)
              upsert list_entry from the remote list
              new entry with no series  -> create series + enqueue match_search
              new entry with a series   -> nothing (dedupe across providers)

match_search(series)
              sources.search(titles + synonyms) -> series_candidate
              set series.needs_review = true
              STOPS. The user confirms in the interface -> creates source_mapping
                                                        -> enqueues chapter_discover

cron 2h ──> chapter_discover(series)      [only series with an active mapping]
              sources.list_chapters(url) -> upsert chapter (state = known)
              komga.books_of(series)     -> mark existing ones as downloaded
              delta -> enqueue download_batch ONLY if series.auto_download
                       otherwise it stops here and the Library shows what is missing

download_batch(chapters)                  [N in parallel]
              subprocess manga-downloader --format cbz, range "1-20,22,25-30"
              progress = archives written over the batch total
              inject ComicInfo.xml, write .part, rename to the final path
              state = downloaded -> enqueue komga_scan (debounced)

komga_scan    triggers a library scan, waits for indexing, matches komga_book_id

progress_push reads read-progress from Komga, writes to MyAnimeList and AniList
```

The manual button in the interface enqueues `download_batch` or `chapter_discover` with
`priority = 0`, ahead of the cron jobs, with no extra code.

**Why batches.** `manga-downloader` reads a manga's complete chapter index on every invocation. One
job per chapter meant re-reading seven hundred entries to fetch a single file, and under parallelism
MangaDex began answering with HTTP 400. The binary accepts a range (`1-10,12,15-20`), so a batch
costs one index read. The batch size lives in `setting` (default 20): a single job for a whole work
would be a lease held for hours and all-or-nothing on failure.

When the source delivers only part of a batch, the chapters that arrived are written and the ones
that did not go back into the queue as a smaller batch, so nothing is downloaded twice. A chapter the
source does not publish in the requested language ends up isolated in ever smaller batches until it
is marked `skipped`.

There are two deliberate stops, and both exist so that nothing leaves over the network without a
decision from the user.

The first is `match_search`: a new manga on the list does not download by itself until the user
confirms the mapping once.

The second is the download itself. Confirming a mapping tells the pipeline *what* the series is, not
that its whole backlog should be fetched. Discovery keeps running, so the Library can show how many
chapters exist and how many are missing, but downloading begins when the user asks for a range or
marks the series as followed (`series.auto_download`). Without this, confirming 45 mappings queued
tens of thousands of chapters at once.

## Queue, concurrency and failure

Leasing uses `SELECT ... FOR UPDATE SKIP LOCKED` ordered by `priority, created_at`, and writes
`lease_until = now() + 15 minutes`. A job whose lease expires returns to `pending` automatically: a
dead worker does not lose work.

Each worker runs N asyncio tasks, with N coming from `setting` (default 3). Above that there is a
semaphore per `source_site`: too many parallel downloads against the same host produce HTTP 429 and
an IP block.

On failure: `attempts + 1`, exponential backoff of 1, 5 and 25 minutes, `max_attempts = 3`, and then
`state = failed`, visible in the interface with `last_error` and the last lines of `job_event`. A
manual retry resets `attempts`.

A network error and a chapter that does not exist at the source are treated differently: the second
marks the chapter `skipped` instead of entering a retry cycle.

Live progress does not poll. The handler inserts into `job_event` and calls
`pg_notify('jobs', job_id)`. The `api` listens on that channel over a dedicated connection and pushes
over SSE.

## Interface

Four screens.

**Library.** A grid of `series`. Each card carries the cover, the canonical title, badges showing
which lists the series comes from, the count of downloaded chapters over the total, and the state:
mapped, needs review, downloading or failed. Filter by state. This is where the chapter range and the
download button live, along with the toggle that follows new chapters.

**Mapping review.** The queue of series with `needs_review`. For each one: titles and synonyms from
the list on one side, candidates from the source site on the other, with cover, chapter count and
year. One click confirms and starts the pipeline. There is a field for pasting the URL by hand when
the search finds nothing. This screen is the system's bottleneck and gets keyboard shortcuts:
confirming moves straight to the next series.

**Downloads.** A live list over SSE, one row per active job with series, chapter, progress bar and
speed. A failures section with `last_error` and a retry button. A pending section with a count.
Clicking a row opens that job's `job_event`.

**Settings.** Connecting MyAnimeList over OAuth2 PKCE and AniList, concurrency, cron expressions, the
library path, and a manual sync trigger.

### API

```
GET  /api/series?state=              POST /api/series/{id}/mapping        {source_url}
GET  /api/series/{id}/candidates     POST /api/series/{id}/download       {from, to}
GET  /api/series/{id}/chapters       POST /api/series/{id}/auto-download  {enabled}
GET  /api/jobs?state=                POST /api/jobs/{id}/retry
GET  /api/jobs/{id}/events           POST /api/sync/{provider}
GET  /api/events                     (SSE: job.progress, job.done, job.failed, series.updated)
GET  /api/settings                   PUT  /api/settings
GET  /api/auth/{provider}/start      GET  /api/auth/{provider}/callback
```

The interface talks to nothing but this API. In particular, it does not talk to Komga directly.

## Disk and metadata

The shared library volume is mounted writable on `worker` and read-only on `komga`:

```
/manga/{slug}/{slug} - Ch.0012 - Chapter title.cbz
```

The chapter number is zero-padded to four digits, which sorts correctly and is recognised by Komga.
Writing happens to a `.part` file on the same volume, followed by an atomic `rename`: Komga never
indexes a half-written file.

Each CBZ gets a `ComicInfo.xml` populated from MyAnimeList and AniList data: `Series`, `Number`,
`Title`, `Summary`, `Writer`, `Penciller`, `Genre`, `Year`, `Count`, `LanguageISO` and `Web`. Komga
reads it during indexing, which removes the manual metadata work and makes the mobile reader show
complete information.

## Infrastructure

```
postgres    postgres:17, pgdata volume, pg_isready healthcheck
komga       gotson/komga, /config on a volume, /manga read-only, port 25600
api         build ., alembic upgrade followed by uvicorn, port 8000,
            depends_on postgres with condition service_healthy
worker      same image, worker command, /manga writable, adjustable replicas
web         Caddy serving the React build and proxying /api to api, port 8080
bootstrap   one-shot: waits for Komga to answer, creates the library if absent, exits
```

Port 8080 on `web` is the only one exposed for normal use. Komga's 25600 stays exposed for the mobile
and web readers.

**Komga bootstrap.** The `bootstrap` service polls Komga's health endpoint and then calls
`komga.ensure_library()`, which idempotently creates the library pointing at `/manga` with the name
defined in `.env`, checking first whether it already exists.

Creating the initial administrator was verified against a live instance and does not require the web
interface: `GET /api/v1/claim` reports whether the instance has been claimed, and `POST /api/v1/claim`
with the `X-Komga-Email` and `X-Komga-Password` headers creates the first user. `bootstrap` does this
when `KOMGA_USER` and `KOMGA_PASS` are set.

**Authentication.** Komga accepts `X-API-Key` or basic authentication on every endpoint. The API key
is preferred because it can be revoked on its own; the password is only unavoidable for the claim,
when no user exists yet to own a key.

**Permissions.** Only `worker` runs with `user: "${PUID}:${PGID}"`, because it is the service that
writes the library. `komga` keeps the user from its own image: overriding it prevents writing to
`/config`, where the SQLite database lives, and the result is a `SQLITE_CANTOPEN` restart loop whose
message never mentions permissions. Komga only reads the library, and world-readable files are
enough.

**Shared image.** `api`, `worker` and `bootstrap` are the same program with different entrypoints and
declare the same `image:`. Without that, rebuilding one leaves the others running old code, and the
symptom is a job failing with "no handler registered".

**Logs.** Every service uses the `json-file` driver with `max-size: 10m` and `max-file: 3`, so the
disk does not fill up silently. The operational log that matters is `job_event`, shown in the
interface; container stdout is for when a container does not start.

**Configuration.** `.env` only: `POSTGRES_*`, `KOMGA_URL`, `KOMGA_API_KEY`, `KOMGA_USER`,
`KOMGA_PASS`, `KOMGA_LIBRARY_NAME`, `MAL_CLIENT_ID`, `MAL_CLIENT_SECRET`, `ANILIST_CLIENT_ID`,
`ANILIST_CLIENT_SECRET`, the optional `MANGADEX_*` personal client values, `PUBLIC_BASE_URL`, `PUID`,
`PGID`, `LIBRARY_PATH`, `DOWNLOAD_CONCURRENCY`. A `.env.example` is versioned and `.env` is in
`.gitignore`. OAuth tokens obtained at runtime live in the `provider_token` table, never in `.env`.

## Tests

The four pure edges, `providers`, `sources`, `downloader` and `komga`, are tested against responses
recorded as fixtures, with no network access in continuous integration.

The `queue` is tested against a real Postgres, covering concurrent leasing, lease expiry and backoff.
Those are the behaviours that fail in production and not in a mock.

The `handlers` are tested with fake implementations of the edges.

An end-to-end smoke test brings up `docker-compose`, creates a fictitious series, confirms a mapping,
downloads a dummy file and checks that the CBZ is at the right path with a valid `ComicInfo.xml`.

## Phases

Each phase delivers something usable on its own.

1. **Skeleton.** `docker-compose`, migrations, a queue with leasing and retry, one trivial handler,
   live SSE. Validates the infrastructure before any domain exists.
2. **Lists.** AniList and MyAnimeList, OAuth, `list_sync`, dedupe into `series`. The Library screen
   starts reading real data.
3. **Matching.** `sources.search`, the Review screen, `source_mapping`.
4. **Download.** Subprocess, progress, `ComicInfo.xml`, atomic writes, the Downloads screen.
5. **Komga.** Library bootstrap, scanning, reconciling `chapter.state` against the books.
6. **Closed loop.** `progress_push` from Komga to MyAnimeList and AniList.

Phases 1 to 5 form the complete system for daily use. Phase 6 is convenience, and comes last because
it depends on write scope at both providers.

## Risks

`manga-downloader`'s output contract is not a stable API; parsing stdout breaks if the format
changes. The parser is isolated in a single module with fixtures, so the fix stays local.

Source sites change their layout and block by IP. The per-host semaphore and the backoff reduce the
problem but do not remove it; the failure is visible in the interface rather than silent.

Writing progress to MyAnimeList and AniList is the only path in this design not yet exercised against
the real service, because it depends on connected accounts. Reading progress from Komga and the rest
of the loop were verified against a live instance.
