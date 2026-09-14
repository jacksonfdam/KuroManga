# Architecture

## Processes

Six services in `docker-compose.yml`.

| Service | What it is |
|---|---|
| `postgres` | The only datastore. Domain, queue and history |
| `api` | FastAPI. REST and the SSE stream. Runs migrations on start |
| `worker` | The job loop and the cron that feeds it. Scalable |
| `web` | Caddy, serving the built interface and proxying `/api` |
| `komga` | The library server and reader |
| `bootstrap` | One-shot: claims Komga if needed, creates the library, exits |
| `comick` | Optional self-hosted source |

**`api`, `worker` and `bootstrap` are the same program with different entrypoints**, and declare the
same `image: kuromanga:local`. Build one and recreate the others, or they run stale code — the
symptom is a job failing with `no handler registered`, which reads as a code bug and is a build bug.

```bash
docker compose build api && docker compose up -d --force-recreate api worker
```

They are separate processes so that restarting the API does not kill a download in flight, and so
the worker can scale independently.

## Module boundaries

```
backend/app/
  providers/   list providers: MyAnimeList, AniList, MangaBaka
  sources/     chapter sources: MangaDex, Comick
  downloader/  the binary subprocess, CBZ writing, ComicInfo
  komga/       the library server client and bootstrap
  queue/       enqueue, lease, complete, fail, notify
  handlers/    one per job type; stitches the above together
  api/         routes and SSE
```

**The four edges — `providers/`, `sources/`, `downloader/`, `komga/` — are pure.** They take
arguments, return values, and never touch the database. Only `handlers/` writes.

That is not style. It is what lets those four be tested against recorded fixtures with no network and
no Postgres, which is most of the suite. A database call inside a provider breaks that and will be
rejected in review.

**The API is a thin layer.** Business rules live in handlers, not in routes. A route validates,
enqueues or reads, and returns.

## Two deliberate stops

Both exist so nothing leaves over the network without a decision.

1. **`match_search` parks candidates and waits.** A wrong automatic match downloads the wrong manga
   for every future chapter. One click per series, remembered forever, is the cheaper trade.
2. **Downloading waits for an explicit range or for `series.auto_download`.** Confirming a mapping
   says what a series *is*, not that its backlog should be fetched.

Discovery and Unmatched follow the same principle: a suggestion is approved by a person, and the
Unmatched screen searches only when asked.

**Do not remove a stop to make something more automatic.** They are the product, not friction in it.

## Live progress

A handler inserts into `job_event` and calls `pg_notify('jobs', ...)`. The API holds one dedicated
asyncpg connection with `LISTEN` on that channel and pushes to the browser over SSE. Nothing polls,
anywhere. A screen that polls is doing it wrong.

## Concurrency

The worker runs N asyncio tasks, N from the `download_concurrency` setting, default 3.

Above that sits **a semaphore per source site** (`downloader/limits.py`). Parallelism across sites is
free; parallelism against one site earns a rate limit or an IP block. Any new code that reaches a
source must take that semaphore.

## The interface

`frontend/src/` is a token layer, presentational primitives in `ui/`, one folder per screen in
`features/`, and shared non-visual code in `lib/`.

Four rules, each of which cost time when broken:

- **`tailwind.config.ts` is the only place a colour, size, radius or spacing value lives.** No hex,
  px or rem literal belongs in a component.
- **A Tailwind class is only real if the built CSS contains it.** A class can look right, typecheck,
  build clean and generate nothing — a name built by string interpolation is never seen by the
  scanner; `font-label-md` does not exist where the scale lives under `fontSize`, so `text-label-md`
  already carries size and weight; `bg-secondary/12` needs `/[0.12]` because the modifier takes scale
  steps. All three fail identically and silently. Verification is `grep` over `frontend/dist/` after
  a build: **the source is what lies, the build output is what tells the truth.**
- **Feature folders never import from each other.** Anything two screens need goes in `ui/` or
  `lib/`. A small duplicated helper is cheaper than a cross-feature edge.
- **No screen renders a number the API cannot serve.** An invented figure that fills a gap in a
  mockup is worse than the gap.

A screen's own data goes through `lib/useAsyncData.ts`, which decides how a request that has not
landed, one that failed, and a refresh that failed over loaded data each look. Built one screen at a
time, they did not agree.

## Testing

| Layer | How |
|---|---|
| The four pure edges | Recorded fixtures, no network |
| `queue` | A real Postgres. Concurrent leasing, lease expiry, backoff |
| Handlers | Fakes for the edges |
| API | A real database, through `ASGITransport` |

The queue is tested against a real database because concurrent leasing, lease expiry and backoff are
exactly what a mock gets wrong.

**The suite migrates the database itself**, from a session fixture in `tests/conftest.py`. That lives
there rather than in the modules that need it: a module truncating a table without owning that
fixture passes on any database migrated by an earlier run and fails on a fresh one — invisible
locally, and failing every time in CI.

CI runs the same checks on every push and pull request, against a Postgres that is fresh each time,
plus a job that fails any pull request carrying tool attribution.

## Failure handling

Retry at 1, 5 and 25 minutes, three attempts, then `failed` with its error visible in the interface.

**`PermanentError` skips the ladder.** Use it when retrying cannot help. A network timeout is
transient; a chapter the source does not publish is not, and retrying it forever is how a queue
fills with work that will never succeed.

Errors reach the user. `last_error` and the job log are shown on the Downloads screen, so a failure
is something to read rather than something to go looking for in container output.
