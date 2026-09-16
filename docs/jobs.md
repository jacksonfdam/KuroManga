# Jobs

Everything the pipeline does happens as a job. There is no central orchestrator: each handler does
one thing and enqueues the next, so the flow is a chain you follow rather than a schedule you read.

Source of truth: `backend/app/enums.py` for the type list, `backend/app/handlers/` for the payloads,
`backend/app/queue/repo.py` for the mechanics, `backend/app/worker/main.py` for the cron triggers.

## The queue

A job is a row in `job`. A worker claims one with

```sql
select ... from job
 where state = 'pending' and run_after <= now()
 order by priority, created_at
 for update skip locked
 limit 1
```

and sets `state = 'leased'` with `lease_until = now() + 15 minutes`.

`SKIP LOCKED` is what lets several workers pull from the same table without blocking each other. The
lease expiry is what makes a dead worker harmless: `reclaim_expired()` returns anything whose lease
has passed to `pending`, so the work is retried rather than lost.

**Priority is ascending — 0 runs before 100.** Anything a person asked for is enqueued at 0 so it
overtakes cron work without a second queue.

**Deduplication** is a partial unique index over `(type, dedupe_key)` restricted to `pending` and
`leased` rows. `enqueue()` returns `None` when an identical job is already waiting. A finished job
never blocks a later identical one, which is what makes a cron that fires while work is queued a
no-op rather than a pile-up.

**Failure** increments `attempts` and schedules a retry at 1, 5 and 25 minutes
(`BACKOFF_BASE_SECONDS * BACKOFF_FACTOR ** (attempts - 1)`). After `max_attempts`, default 3, the
job is `failed` and stays visible with its `last_error`. Raising `PermanentError` from a handler
skips the ladder entirely — use it when retrying cannot help, such as a chapter the source does not
publish.

**Progress** is an `INSERT` into `job_event` plus `pg_notify('jobs', ...)`. The API holds one
dedicated connection with `LISTEN` on that channel and pushes to the browser over SSE. Nothing
polls. A handler that runs for a long time should call `renew_lease()` as it reports, or it will be
reclaimed mid-flight.

## The chain

```
cron ──> list_sync ──> match_search ──┐
                                       │ (user confirms a source mapping)
                                       ▼
cron ──> chapter_discover ──> download_batch ──> komga_scan
                                       │
cron ──> progress_push ────────────────┘

cron ──> anime_list_sync ──> suggest_build ──┐
                                              │ (user approves a suggestion)
                                              ▼
                                          list_write
```

## Every job type

### `list_sync`
**Payload** `{provider}` · **Enqueues** `match_search` for each new series

Reads a provider's manga list and folds it into `series`. Resolution order in `resolve_series()`:
an existing `list_entry` for this exact `(provider, provider_media_id)`, then a cross-reference
match, then a normalised-title match, then create. See [`providers.md`](providers.md) for why
cross-references outrank titles and what makes one authoritative.

### `match_search`
**Payload** `{series_id}` · **Enqueues** nothing

Searches the configured sources and writes `series_candidate` rows, then **stops**. This is the
first deliberate stop: a wrong automatic match downloads the wrong manga for every future chapter,
so a person confirms once and the mapping is remembered. Confirming is an API call, not a job.

### `chapter_discover`
**Payload** `{series_id}` · **Enqueues** `download_batch`, only if `series.auto_download`

Lists chapters at the mapped source, upserts `chapter` rows, reconciles against what Komga already
holds, then queues the difference — **only for a series the user has opted in**. This is the second
deliberate stop. Confirming a mapping says what a series *is*, not that its backlog should be
fetched.

### `download_batch`
**Payload** `{chapter_ids}` · **Enqueues** `komga_scan`

Downloads several chapters in one job. Batching outlived the reason it was introduced: the old
download binary re-read a manga's entire chapter index on every invocation, so one job per chapter
meant re-reading seven hundred entries per file. On the Python path a chapter costs one request, and
a batch now exists to size the lease and amortise the series metadata read — a single job for a
whole backlog would hold one lease for hours and fail all or nothing. Size is the
`download_batch_size` setting, default 20.

Partial results are kept and the remainder requeued as a smaller batch, so nothing downloads twice.
A chapter the source will not serve ends up isolated in ever-smaller batches until it is `skipped`.

Progress is reported as **pages fetched within the current chapter, and chapters within the batch** —
`chapter 13: 30/30 pages (2/20 chapters)`. It used to count the archives on disk, because the tool
that wrote them reported a percentage that restarted with every chapter and said nothing about the
batch. The page list now says how many pages a chapter has before the first one is fetched, so there
is nothing left on disk that the handler does not already know.

The job lease is renewed from inside that count, every twenty pages. Renewing once per chapter is not
enough: two hundred pages against a site that declared one request every ten seconds outlasts the
fifteen-minute lease on its own, and an expired lease hands the same batch to a second worker.

### `download_chapter`
**Payload** `{chapter_id}` · **Enqueues** `komga_scan`

One chapter. Retained for a manual single retry; the pipeline uses `download_batch`.

Both handlers take the same path: resolve the source from the registry by the chapter's own URL, list
its pages, fetch them through the site's client, write the archive, place it, mark it. A chapter the
source will not serve raises `ChapterUnavailable` and is `skipped` rather than retried — in a batch
that skips the one chapter, not the other nineteen.

### `komga_scan`
**Payload** `{series_id}` · **Enqueues** nothing

Triggers a Komga library scan, polls until the series appears, then copies Komga's book ids onto
`chapter` rows, matching by file path. Debounced by `dedupe_key`, so a burst of finished downloads
becomes one indexing pass.

### `progress_push`
**Payload** `{series_id}` · **Enqueues** nothing

Reads what Komga records as read and writes it to every connected list. **Forward only**: a write
that would lower a provider's recorded progress is dropped, never sent.

### `progress_write`
**Payload** `{series_id, chapter}` · **Enqueues** nothing

Writes an explicit chapter number, from the interface rather than from Komga. Shares the forward-only
guard.

### `status_write`
**Payload** `{series_id, status}` · **Enqueues** nothing

Writes reading status. Separate from progress on purpose: **a status write never carries progress**.
Marking a series complete must not zero a counter on someone else's service.

### `notes_write`
**Payload** `{series_id}` · **Enqueues** nothing

Writes the user's note and rating back to the providers that accept them.

### `anime_list_sync`
**Payload** `{provider}` · **Enqueues** `suggest_build`

Reads the anime side of a list, with the relation edges naming which manga an anime adapts, into
`anime_entry`. A provider with no anime side returns nothing rather than failing — `fetch_anime_list`
has a default. This is why a third list provider makes the discovery refresh queue three jobs.

### `suggest_build`
**Payload** none · **Enqueues** nothing

Materialises `suggestion` rows from anime relations, deduplicated by manga identity and ranked, each
carrying the reason it exists. A manga already in `series` or `list_entry` must not surface, and a
dismissal persists so the same title never returns.

### `list_write`
**Payload** `{suggestion_id, status}` · **Enqueues** nothing

Approving a suggestion, written to every destination at once. A transient failure at one destination
retries only that one rather than replaying the successes.

### `media_enrich`
**Payload** `{series_id}` · **Enqueues** nothing

Fills metadata a list provider did not supply.

## Adding a job type

1. Add the member to `JobType` in `backend/app/enums.py`.
2. Create `backend/app/handlers/<name>.py` with a function decorated `@register(JobType.X)`.
3. **Import it in `backend/app/worker/main.py`** — importing the module is what registers the
   handler. A job whose module is never imported fails with `no handler registered`, which reads
   like a code bug and is an import bug.
4. Give it a `dedupe_key` if a cron can enqueue it more than once.
5. Raise `PermanentError` for anything retrying cannot fix.
