# Discovery: suggesting manga from the anime list, synchronised across four destinations

Date: 2026-09-13
Status: approved for planning

## Problem

The anime list and the manga list are separate lists on MyAnimeList and AniList, and they do not talk
to each other. An anime watched to the end puts the corresponding manga nowhere: either the user
remembers to look the title up and add it by hand, on both providers, or the story simply stops where
the adaptation stopped.

The current pipeline only sees what is already on the manga list. It resolves a title to a source
URL, downloads chapters as CBZ and hands them to Komga, but the entry has to exist first. What is
missing is the layer before that: look at the anime list, find out which manga each anime adapts,
discard what is already being read, and offer the rest as a suggestion — with the reason in plain
sight, so the decision is one click.

Approving a suggestion has to have the same effect as adding the manga by hand in four places:
MyAnimeList, AniList, MangaDex and the Komga library.

## Scope

In:

- Reading the anime list on MyAnimeList and AniList, with the relations that link an anime to a
  manga.
- Materialising suggestions, deduplicated by manga identity, with a ranking and a reason.
- The Discovery screen: approve with a chosen status, with a download-now control per item, or
  dismiss for good.
- Writing the status to MyAnimeList, AniList and MangaDex.
- Integrating `comick-source-api` as the search and chapter-listing layer for sites outside MangaDex.

Out:

- Recommendation by taste, genre or similarity. The only reason a suggestion appears is that an anime
  on the list adapts that manga.
- A new page extractor. `manga-downloader` already supports 84 sites, including the ones that come in
  here; downloading does not change.
- Progress synchronisation. Progress remains the exclusive business of `progress_push`.

## Decisions and reasons

**AniList first, MyAnimeList as the fallback.** AniList exposes the media relation graph
(`relations { edges { relationType node { ... } } }`) in the same query that returns the list, so
resolving an anime to a manga costs no request beyond what would be made anyway. MyAnimeList has
`related_manga`, but only in each anime's detail (`/anime/{id}`), one request per title. Fetching
that detail only for what AniList did not resolve turns a preference for accuracy into saved
requests. **This fallback was removed after shipping — see "As built" below.**

**Its own subsystem, not an extension of what exists.** A suggestion is not a series. Keeping
suggestions in `series` behind a flag would force every Library, downloader and Komga query to carry
a `where not suggested` — coupling that charges interest on every future feature. Two new tables
isolate what is not yet a library from what already is.

**Persisted state, not a live computation.** A large anime list spends rate limit every time the
screen is opened, and "dismiss" needs somewhere to live. The state would have to exist either way;
materialising solves both at once.

**comick searches, the binary downloads.** `comick-source-api` returns, per chapter, only
`{id, number, title, url, group, lastUpdated}` (`src/types/index.ts`): the URL of the page on the
site, never the image. There is no pages endpoint — the official companion is a userscript that
extracts images in the browser. That would make comick useless as a download source, if
`manga-downloader` did not already download from the same sites. The usable set is the intersection
of the two catalogues: comick finds and lists, the binary downloads.

**Self-hosted comick.** Putting a third party's scraping in the pipeline's critical path means
depending on the availability of an instance maintained as a courtesy. The service requires no
environment variable at all and comes up in Docker.

## Data model

Two new tables, no column changed in the existing ones.

```
anime_entry                          -- mirror of the anime list, one per provider
  id                bigint pk
  provider          varchar(20)      -- unique(provider, provider_media_id)
  provider_media_id varchar(50)
  title_romaji, title_english
  synonyms          jsonb
  status            varchar(20)      -- ListStatus; READING means watching
  progress_episode  int
  total_episodes    int null
  cover_url         text null
  related_manga     jsonb            -- [{provider, media_id, relation, format}]
  raw               jsonb
  updated_at        timestamptz

suggestion                           -- a candidate manga, not an anime row
  id                bigint pk
  provider          varchar(20)      -- unique(provider, provider_media_id)
  provider_media_id varchar(50)      -- the manga's identity; AniList wins when both exist
  alt_ids           jsonb            -- {mal: "123"} when the other provider knows the title
  title             varchar(500)
  cover_url         text null
  total_chapters    int null
  year              int null
  publishing_status varchar(20) null -- RELEASING / FINISHED / HIATUS
  state             varchar(20)      -- new | dismissed | added
  rank_score        numeric(5,4)
  series_id         bigint null fk series(id) on delete set null
  meta              jsonb
  created_at, updated_at timestamptz
```

`suggestion.meta` carries what the screen and the write need without querying anything else: the
anime of origin (id, title, status, episodes), the relation type, the signals that formed the
ranking, the MangaDex UUID when one was found, the sources found through comick
(`[{site, url, chapters, score}]`) and the result of the last write per target
(`write_results: [{target, ok, error, at}]`).

Enumerations: `SuggestionState` is new; `JobType` gains `ANIME_LIST_SYNC`, `SUGGEST_BUILD` and
`LIST_WRITE`. `ListStatus` is untouched — anime and manga share the same five states, and only the
label in the interface changes.

**Identity.** The suggestion belongs to the manga, not to the anime. Two `anime_entry` rows for the
same title, one per provider, collapse into a single row; when both know the manga, the AniList id
becomes the identity and the MyAnimeList one goes into `alt_ids`. That pair is what the status write
uses later, with no extra lookup.

**Exclusion.** A manga does not become a suggestion when its `provider_media_id` is already in
`list_entry`, when its title matches `series.meta -> aliases` through the same alias function
`list_sync` uses, or when its suggestion is `dismissed`. Dismissal is permanent: the row stays, with
its state, precisely so that the next cycle cannot resurrect it.

## Jobs

### `ANIME_LIST_SYNC`

A new cron, `cron_anime_list_sync`, default `0 */12 * * *`. Per connected provider:

- AniList: `MediaListCollection(type: ANIME)` with `relations` embedded. One query for the whole
  list, relations included.
- MyAnimeList: `/users/@me/animelist` for the list; `/anime/{id}` only for the titles AniList did not
  resolve.
- Upsert into `anime_entry` by `(provider, provider_media_id)`.
- On finishing, enqueue `SUGGEST_BUILD` with a dedupe key, the way `list_sync` already does with
  `match_search`.

### `SUGGEST_BUILD`

A computation over what is already in the database, plus manga metadata:

1. Read `anime_entry` rows whose status is not dropped.
2. Extract from `related_manga` the `SOURCE` and `ADAPTATION` edges whose node is a manga; discard
   `LIGHT_NOVEL`, `NOVEL` and `ONE_SHOT`.
3. Collapse by manga identity and fill in `alt_ids`.
4. Discard what is already in `list_entry`, what is already a `series` and what is `dismissed`.
5. Fetch metadata in batches (`Page(media: ids)` on AniList, 50 per query): cover, chapter count,
   publishing status. Fetch the MangaDex UUID and the comick sources too.
6. Compute `rank_score` and upsert, preserving `state`.

**Ranking**, three signals added together: a finished anime whose manga is still publishing (the
heaviest), an anime still running, and a manga with chapters beyond what the adaptation covered. The
episode-to-chapter estimate enters as a weight and as a sentence on the card, never as a filter: it
gets things wrong, and being wrong must not hide a title.

### `LIST_WRITE`

Writes the chosen status to the providers. A job, not a call inside the request: three external APIs
fail independently, and the request has to return quickly while the screen follows the result through
the events.

The targets are independent, each one's result is recorded in `meta.write_results`, and a retry
repeats only the ones that failed. Writing a status is idempotent, so repeating it costs nothing. A
target with no connected account raises `PermanentError` naming the provider, instead of retrying for
ever.

## Approval

`POST /api/suggestions/{id}/add` with `{status, download}`:

1. Create `series` with the same `reserve_slug` and the same set of aliases `list_sync` uses, and
   create the local `list_entry` rows — without them, the next `list_sync` would bring the same manga
   back as a new entry, for review.
2. Enqueue `LIST_WRITE`.
3. Mapping: the suggestion already carries the best source candidate. With high confidence, write
   `source_mapping` directly and skip the Review screen; otherwise `needs_review` stays true and the
   flow is today's.
4. `download: true` enqueues `CHAPTER_DISCOVER` immediately. The toggle comes pre-set from the status
   — on for Reading and Plan to Read, off for Completed, On Hold and Dropped — and is flipped per
   item on the screen.
5. Mark `state = added` and fill in `series_id`.

## Synchronisation by destination

| internal | MyAnimeList | AniList | MangaDex | Komga |
|---|---|---|---|---|
| READING | `reading` | `CURRENT` | `reading` | — |
| PLAN_TO_READ | `plan_to_read` | `PLANNING` | `plan_to_read` | — |
| COMPLETED | `completed` | `COMPLETED` | `completed` | marks downloaded books as read |
| ON_HOLD | `on_hold` | `PAUSED` | `on_hold` | — |
| DROPPED | `dropped` | `DROPPED` | `dropped` | — |

**MyAnimeList**: `PATCH /manga/{id}/my_list_status` with `status`. It is the same endpoint
`push_progress` already uses, so the write scope is already granted and the OAuth flow does not
change.

**AniList**: the existing `SaveMediaListEntry` mutation gains a `status` variable. On both providers,
adding and changing status are the same call: creating the entry is a side effect of writing a status
on media that is not on the list yet.

**MangaDex**: `POST /manga/{uuid}/status`, which requires the MangaDex UUID. It may not exist if the
chosen source is another site, which is why `SUGGEST_BUILD` stores the UUID whenever the search finds
one, whether or not it is the download source. With no UUID, the target is skipped and recorded as an
absence, not as a failure.

**Komga** is not a list, it is a library: there is no adding without downloading. Synchronising with
it is two effects, both already implemented — the CBZ landing in `/manga` with `komga_scan` behind
it, and, when the status is Completed, marking the downloaded books as read through
`set_read_progress`.

**The boundary that must not blur**: `LIST_WRITE` writes status, never progress. Progress stays
exclusive to `progress_push`, which only moves forward. Without that separation, marking a title as
Completed would zero the chapter read on the way back.

## Integration with comick

A `comick` service in `docker-compose.yml`, from the repository's image, with no environment
variable. A new setting, `COMICK_API_URL`, default `http://comick:3000`.

`app/sources/comick_client.py` is pure HTTP — `search(query, source)`, `chapters(url, source)`,
`sources()`, `health()` — testable from fixtures like the other clients.

The registered sources come out of the intersection between what comick can search *server-side* and
what `manga-downloader` knows how to download. comick also proxies asurascan through
`/api/proxy/html`, but asurascan is flagged `clientOnly` and, checked against the running service,
its scrape returns zero results outside a browser — it only works through the companion userscript,
which this pipeline does not run. The registered set is **weebcentral** alone. It becomes a `Source`
registered by a parameterised subclass `ComickSource(site, domains)`, so that `source_for_url` keeps
resolving a hand-pasted URL and `download_chapter` does not change a line. Adding a site later is one
entry in the registration table, and only once its scrape works from the server.

MangaDex stays preferred on the tie-break: a documented API, reliable chapter numbering and personal
authentication already configured.

**Degradation**: comick being unavailable does not bring Discovery down. The suggestion is still born
from the relation graph, only without the source list, and approving it falls through to Review.
comick's `/api/health` feeds the state shown in Settings.

## Interface

Routes in `app/api/routes_discovery.py`:

- `GET /api/suggestions?state=new&limit=&offset=`, ordered by `rank_score` descending.
- `POST /api/suggestions/{id}/add` with `{status, download}`.
- `POST /api/suggestions/{id}/dismiss`.
- `POST /api/discovery/refresh`, which enqueues `ANIME_LIST_SYNC` for whoever does not want to wait
  for the cron.

A Discovery screen, the fifth item in the nav, with a badge counting `state = new` in the same
pattern as the Review badge. One card per suggestion, in a grid like the Library, carrying the cover,
title, year and chapter count; the reason for the suggestion, which is what distinguishes this screen
from any other list ("from *Vinland Saga*, anime finished — the manga runs on to chapter 210"); chips
for the sources found, with the preferred one highlighted; the status select; the download-now
toggle; and the add and dismiss buttons. `useJobEvents` refreshes the card when `LIST_WRITE`
finishes.

Settings gains the new cron and comick's health state.

## Errors and limits

AniList accepts around 90 requests per minute: the whole list comes out in one query and the manga
metadata in batches of 50. MyAnimeList is only queried for the detail of the anime AniList did not
resolve. A network failure on either is retried by the queue that already exists, with the same
backoff as every other job. comick being down degrades the screen, it does not break it.

## Tests

Along the split the project already uses — a pure parser from fixtures, a handler against the
database.

Fixtures: an AniList response with `relations`, MyAnimeList's `related_manga`, comick's `search` and
`chapters`.

Pure: extracting the manga edges from the graph; collapsing identity across providers; `rank_score`;
the status map for the four destinations.

Handlers: `ANIME_LIST_SYNC` idempotent on the upsert; `SUGGEST_BUILD` neither resurrecting
`dismissed` nor suggesting what is already in `list_entry`; `LIST_WRITE` with one target failing and
two passing, and the retry touching only the one that failed.

Flow: approving creates `series` and `list_entry`, marks `added`, and with `download: false` does not
enqueue `CHAPTER_DISCOVER`.

## Acceptance criteria

1. The anime list from both providers appears in `anime_entry` after one sync cycle.
2. An anime whose manga is already on the manga list produces no suggestion.
3. A dismissed suggestion does not come back on the next cycle.
4. Approving with the status Reading creates the entry on MyAnimeList, AniList and MangaDex with the
   matching status.
5. Approving with `download: false` downloads nothing and still records the status on all three
   providers.
6. Approving with `download: true` and a confident candidate downloads without going through the
   Review screen.
7. A failure on one provider does not prevent the write on the other two, and the retry repeats only
   what failed.
8. comick being unavailable still produces suggestions, without the source list.

---

## As built

Written after the implementation (branch `feat/anime-manga-discovery`, PR #19), with the design above
left intact: that is the record of what was decided, this section is the record of what was built.
Where the two disagree, this section holds.

### MyAnimeList's fallback was built, then removed: it cannot work

The fallback described above shipped as designed: `ANIME_LIST_SYNC` called
`/v2/anime/{id}?fields=related_manga` once for every MyAnimeList anime AniList had not already
resolved. Nobody had checked that endpoint against the live API first. After a completed sync the
database held 970 MyAnimeList anime rows and 0 with a relation, so it was checked directly:

```
GET /v2/anime/21?fields=related_manga          -> {"id":21,"title":"One Piece","related_manga":[]}
GET /v2/anime/37521?fields=related_manga       -> related_manga: []
GET /v2/anime/37521?fields=id,title,related_manga{node{id,title}},related_anime
                                               -> related_manga: [], related_anime: 2 entries
```

One Piece and the other title both obviously have a source manga, and the request syntax itself
works — the same nested-field form returns real data for `related_anime` on the same call. MyAnimeList's
v2 API simply never populates `related_manga` on the anime endpoint; that field only ever links manga
to manga, not anime to manga. The fallback was pure cost: about 970 requests against the user's
account every twelve hours, for zero relations, ever. It was removed (`fetch_related_manga`,
`parse_related_manga`, `needs_mal_relations`, and the per-anime branch in `ANIME_LIST_SYNC`) rather
than kept dormant, so nobody spends a future cycle re-adding it on the same assumption. Reading the
MyAnimeList anime list itself is unaffected — only the relation lookup was dead.

### Approval resolves before it creates

The design says to create `series`. The implementation looks first: by media id, then by alias,
exactly as `list_sync` does, and only creates when it found nothing (`resolve_series_for`, in
`app/api/routes_discovery.py`). A suggestion can sit for weeks without an answer, and a `list_sync`
in the meantime creates the same manga under its own spelling: creating it again here would mean two
slugs, two folders and two series in Komga.

Two consequences of that, which the design did not foresee because it did not foresee the resolution:

- The reused series may already have an active `source_mapping`, confirmed by the user. Approval does
  not write a second one over it, not even when the candidate is confident.
- The local write became `upsert_entry_status`, not `list_sync`'s `upsert_entry`. The shared upsert
  copies every column on conflict, and a DTO built from a suggestion carries no progress: approving a
  manga `list_sync` already knew zeroed `user_progress_chapter` and wiped the title, cover and `raw`.
  That counter is the only monotonic guard there is — `progress_push` compares against it — so
  zeroing it would push out to the real account a chapter lower than the one it already has. That
  separation is what makes this spec's "boundary that must not blur" hold, not the name of the job.

### Automatic mapping requires an identical title, not just a score

The design says "high confidence". The score alone will not do: it comes from one spelling while
`match_search` scores against all of them, so the near miss sits right on the line — "Dragon Ball"
against "Dragon Ball Super" gives 0.786. The criterion as implemented is 0.80 **and** a normalised
title equal to the suggestion's; the candidate's title is now stored in `meta.best` alongside site,
url and score, precisely for that comparison. The rest goes to Review, which is where a human sees
what was rejected.

### "Baixar agora" is additive, and survives Review

Two corrections to step 4 of Approval:

- The flag becomes `auto_download = auto_download or :enabled`. Assigning the checkbox's value turned
  off following for a series the user was already following — and the box starts unchecked on
  Completed, On Hold and Dropped, which is the common case.
- An immediate `CHAPTER_DISCOVER` only when the mapping came out resolved. When it falls through to
  Review, the download request stays in the flag and `confirm_mapping` honours it when it enqueues
  its own `CHAPTER_DISCOVER`. Without this, whoever asked for a download and landed on Review would
  review the series and never get the download.

### `LIST_WRITE`: a missing account is not a job failure

The design says to raise `PermanentError` for a target with no connected account. Implemented that
way, a disconnected AniList retired the job before MyAnimeList and MangaDex were written. What exists
instead:

- `NotConnected` is recorded against the target and the loop carries on. It only becomes a
  `PermanentError` if, at the end, nothing was written and nothing can be: reconnecting is a human
  action, and retrying does not help.
- `NotConfigured` — MangaDex without the `MANGADEX_` variables, which are optional in `.env.example`
  — is recorded as `skipped`: an absence, the same shape the spec gives a suggestion with no UUID. A
  real MangaDex error still fails and still retries.
- `meta.write_results` gained a `skipped` field because of this, and the screen lists only the
  targets that actually failed, with the time.

The targets are the ones the suggestion knows: its own provider, those in `alt_ids`, and MangaDex
when the UUID resolved. Never all three unconditionally.

### Where the MangaDex write lives

There is no `providers/mangadex.py`. MangaDex is not a user list in the sense the other two are —
there is no OAuth here — so `POST /manga/{uuid}/status` went into `sources/mangadex.py` as
`set_reading_status`, using the personal token cache that was already there. And `ListSource` gained
a single `set_status`: on both providers, adding to the list and setting a status are the same call,
so two methods would be two names for one thing.

### Komga: marked once, and only the first batch

Marking as read became a step of `komga_scan`, after the books' adoption is committed (those ids are
what `progress_push` reads; a failure against Komga must not undo them), with a per-book error
handled individually and a `meta.komga_marked_read` stamp so it does not repeat. The stamp is the
known limitation: `chapter_discover` enqueues every batch at once and each batch ends with its own
scan, so a long work has only the books indexed in the first one marked. It is in issue #21 and was
not fixed here.

### Long jobs commit per unit of work

`SUGGEST_BUILD` does one search per source per seed, and `ANIME_LIST_SYNC` one request per
MyAnimeList anime: both overrun the 900-second lease on a real list, and an expired lease goes back
to the pool and is leased again — the job would end up running beside itself. Each now commits and
renews the lease per unit (one seed; twenty anime).

### Two economies the design did not ask for

- A seed that is already `dismissed` is discarded along with the ones already in `list_entry`, before
  the search. Preserving `state` in the upsert was enough for correctness; the cost was that it was
  not enough — every dismissal added one search per source to every future cycle.
- `source_summary` omits the keys it did not find instead of writing them null. The upsert merges
  `meta` shallowly, so a cycle with MangaDex down would erase the UUID the status write depends on.

### comick's search contract is `source`, singular, and a flat list

The fixtures this was first built against were invented rather than recorded against the pinned
service, and got the contract wrong in two ways: the client sent `{"query", "sources": [...]}`
(plural) instead of `{"query", "source": "<one id>"}`, and the parser expected `results` to be
per-source groups holding a `manga` list. Neither shape exists. A single `source` gets back a flat
`results` list for that scraper; the grouped, `manga`-keyed NDJSON shape only appears when `source`
is omitted or `"all"` — a branch this client never takes on purpose. With the plural key, `source`
was always undefined server-side, the endpoint always took the streaming branch, and
`payload["results"]` never matched what `parse_search` looked for: comick contributed zero
candidates, silently, and the tests never caught it because they were checked against the same
invented shape. Fixed by sending singular `source` and reading `results` flat; the fixtures were
re-recorded from the live service.

Checking the live service also settled which sites belong in `SITES`: asurascan is registered on
comick but answers with an empty `results` list for every query run from the server, because its
scrape only runs through a browser userscript. It is not in `SITES`, see above.

### comick pinned to a commit

The design says "from the repository's image". `docker-compose.yml` pins
`#ea168fc283466c403d057301df41fc177694c67c`: without a ref, every build brings up on this host
whatever that third party pushed to the default branch. Updating it means swapping the SHA after
reading what changed. The page extractor stays out, as the scope already said: comick has no image
endpoint, and `manga-downloader` downloads from the same sites.

In Settings, comick appears as `reachable` / `not answering`, not as an account: it has no login at
all, and the reused provider row said "signed in".

### Known gaps

- The format filter (`LIGHT_NOVEL`, `NOVEL`, `ONE_SHOT` out) only works on AniList, whose edges carry
  `format`. MyAnimeList exposes no anime→manga relation at all (see "As built" above), so a MAL-only
  account gets no automatic suggestions, filtered or not.
- A suggestion that has stopped being a suggestion — the manga was added by hand on the provider —
  stays `new`, because the rebuild never touches `state`. The card sits there and the badge
  overcounts.

That one, and the smaller ones, are in issue #21.
