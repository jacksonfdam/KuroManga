# Series Detail — Complete Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring `/series/:id` to the redesign mockup — publisher breadcrumb, native title, author credit, score/ranking strip, a progress manager that writes list status, synopsis with official metadata, similar works, characters and private notes — serving every one of them from a provider field that was verified to exist.

**Architecture:** Neither provider payload needs a migration: `list_entry.raw` is JSONB and already stores whatever the provider returned, so widening the AniList `LIST_QUERY` and the MyAnimeList `LIST_FIELDS` enriches it in place on the next `list_sync`. A new pure module, `app/api/series_metadata.py`, normalises both provider shapes into one `metadata` block that `GET /api/series/{id}` returns alongside `series`. Fields too heavy to fetch for a whole list (characters, recommendations, rankings, score distribution) are fetched per-series by a new `media_enrich` job into `series.meta['enrichment']`, enqueued by the detail route when that cache is missing or stale. Writing a list status reuses the shape `progress_write` already established: a route that validates, a deduped job, a handler that writes to every connected provider.

**Tech Stack:** FastAPI + SQLAlchemy async + asyncpg + Postgres; React 18 + TypeScript + Vite + Tailwind (token map in `frontend/tailwind.config.ts`); pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-09-13-web-redesign-design.md` (§ Series detail) and the mockup the maintainer supplied on 2026-09-14 (`stitch_mangashelf_manager (1)/screen.png`).

## Global Constraints

- Everything committed is in **English**: code, comments, commit messages, the interface.
- No commit, PR, issue or comment may reference the tools used to write it. No trailers of any kind.
- Micro commits: one focused change each, self-contained and buildable. Subjects are imperative and scoped (`feat(api):`, `fix(web):`, `test:`).
- **No screen renders a number the API cannot serve.** Every value added here traces to a named provider field listed in "Verified provider contracts" below.
- `frontend/tailwind.config.ts` is the only place a colour, size, radius or spacing value lives. No hex, px or rem literal in a component.
- A Tailwind class is only real if the built CSS contains it. After a frontend task: `npm run build`, then `grep -r "<class>" frontend/dist/` to prove it exists.
- Feature folders never import from each other. Anything two screens need lives in `ui/` or `lib/`.
- A screen's own data goes through `lib/useAsyncData.ts`.
- `providers/`, `sources/`, `downloader/` and `komga/` are pure at their edges — they take arguments and return values and never touch the database. Only `handlers/` writes.
- `alembic` is not on PATH: invoke it as `python -m alembic`. This plan adds **no migration** — verify that claim in Task 1 before relying on it.
- Backend tests need Postgres: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests -q` from `backend/` (start `manga-pg-dev` first, or use a worktree's own container and port).
- Lint: `.venv/bin/python -m ruff check app/ tests/`.

## Verified provider contracts

Read on 2026-09-14 from the providers themselves, not from memory.

**AniList** — GraphQL introspection of `https://graphql.anilist.co`:

- `Media`: `id idMal title type format status description startDate endDate chapters volumes countryOfOrigin isLicensed source coverImage bannerImage genres synonyms averageScore meanScore popularity trending favourites tags relations characters staff isAdult externalLinks rankings mediaListEntry stats siteUrl`
- `MediaList`: `id userId mediaId status score progress progressVolumes repeat priority private notes hiddenFromStatusLists customLists advancedScores startedAt completedAt updatedAt createdAt media user`
- `MediaRank`: `id rank type format year season allTime context`
- `MediaTag`: `id name description category rank isGeneralSpoiler isMediaSpoiler isAdult`
- `Recommendation`: `id rating userRating media mediaRecommendation user`
- `MediaStats`: `scoreDistribution statusDistribution`
- `FuzzyDate`: `year month day`
- Arguments: `MediaList.score(format: ScoreFormat)`; `Media.characters(sort: CharacterSort, role: CharacterRole, page: Int, perPage: Int)`; `Media.staff(sort: StaffSort, page: Int, perPage: Int)`; `Media.recommendations(sort: RecommendationSort, page: Int, perPage: Int)`; `Media.rankings` and `Media.stats` take none.
- Enums: `ScoreFormat = POINT_100 | POINT_10_DECIMAL | POINT_10 | POINT_5 | POINT_3`; `RecommendationSort = ID | ID_DESC | RATING | RATING_DESC`; `CharacterSort = ID | ID_DESC | ROLE | ROLE_DESC | SEARCH_MATCH | FAVOURITES | FAVOURITES_DESC | RELEVANCE`; `MediaRankType = RATED | POPULAR`.

**MyAnimeList** — the manga field list printed in its own API v2 reference:

```
id,title,main_picture,alternative_titles,start_date,end_date,synopsis,mean,rank,
popularity,num_list_users,num_scoring_users,nsfw,created_at,updated_at,media_type,
status,genres,my_list_status,num_volumes,num_chapters,authors{first_name,last_name},
pictures,background,related_anime,related_manga,recommendations,serialization{name}
```

`my_list_status` on manga carries `status score num_volumes_read num_chapters_read is_rereading start_date finish_date priority num_times_reread reread_value tags comments updated_at`.

## Parallel work in flight

This branch is cut from `origin/main` at `78038b6`. A second branch,
`feat/home-screen`, is being built at the same time and is **not merged**. Two
of its changes overlap this plan, and both are handled here rather than waited
for:

- It extracts `app/api/list_raw.py`, moving `_display_fields` out of
  `routes_series.py` so the Home and Stats screens can read the provider
  payload too. Task 3 below creates `app/api/series_metadata.py`, which does a
  strictly larger job on the same two provider shapes. The paths are distinct,
  so the merge is not an add/add conflict — but once both land, the two belong
  in one module, and this branch's pull request must say so.
- It moves `useIncrementFlash` and `QuickIncrement` into `ui/`. Task 11 moves
  the hook to that same destination for that reason.

It also adds a `progress_event` table recording each forward movement of
reading progress. **The mockup's weekday frequency chart is therefore real —
but not buildable from this branch**, because that table is not on `main`. It
is deferred to a follow-up on the same issue rather than built against a table
this branch cannot see. It fills forward, so it will be empty the day it ships
and the panel has to say so rather than drawing a flat line as though nothing
had been read.

---

## What the mockup asks for that nothing can serve

These are **deliberately not built**. The maintainer chose "everything real, drop the unservable" on 2026-09-14. Each is listed so a later reader does not mistake the gap for an oversight.

| Mockup element | Why it is dropped |
|---|---|
| "Frequência Semanal" weekday chart | Deferred, not dropped — see "Parallel work in flight" above. `progress_event` exists on the unmerged `feat/home-screen` branch and makes the chart real; it is not on `main`, so it is not built here. |
| "Lançamento — Semanal / Toda sexta-feira" | Neither provider exposes a manga release cadence. AniList's airing schedule is anime-only. |
| Per-chapter release date and page count | `chapter` stores `number, title, source_url, state, file_path, komga_book_id, discovered_at`. `discovered_at` is when *we* saw it, not when it published, and page count is never read. |
| "ComicInfo.xml Embedded & Validated" / "100% Verificado" | Nothing records a post-write validation of the embedded `ComicInfo.xml`. |
| "Volume 16 · 18 vols" as a *physical* shelf count | Total volumes and volumes read are servable (AniList `volumes` / `mediaListEntry.progressVolumes`, MAL `num_volumes` / `my_list_status.num_volumes_read`) and **are** built. A separate physical-copy count is not tracked and is dropped. |
| "Faltam 24 caps (~2h15m estimadas)" | Built, but labelled an estimate: `reading_minutes_per_chapter` already exists in `app/settings_store.py` (default 8). A number presented as measured when it was assumed is worse than no number. |
| "Estatísticas & Análise" tab | Belongs to the Stats screen and its `progress_event` table. Not a detail-screen tab. |
| "Reler vezes: 0x" when no provider reports it | Servable (AniList `repeat`, MAL `num_times_reread`) and built. Shown only when a provider actually returned it. |

---

## File Structure

**Backend**

| File | Responsibility |
|---|---|
| `app/providers/anilist.py` *(modify)* | Widen `LIST_QUERY`; add `MEDIA_DETAIL_QUERY` and `AniListSource.fetch_media_detail`. |
| `app/providers/mal.py` *(modify)* | Widen `LIST_FIELDS`; add `DETAIL_FIELDS` and `MalSource.fetch_media_detail`. |
| `app/api/series_metadata.py` *(create)* | Pure: `metadata_of(raw, enrichment)` → the `metadata` block. No database, no network. |
| `app/api/routes_series.py` *(modify)* | Detail payload gains `metadata`; new `POST /{id}/status` and `POST /{id}/notes`; detail enqueues `media_enrich` when the cache is cold. |
| `app/handlers/status_write.py` *(create)* | `JobType.STATUS_WRITE`: write one list status to every connected provider. |
| `app/handlers/notes_write.py` *(create)* | `JobType.NOTES_WRITE`: write the private note to every connected provider. |
| `app/handlers/media_enrich.py` *(create)* | `JobType.MEDIA_ENRICH`: fetch the heavy per-media extras into `series.meta['enrichment']`. |
| `app/enums.py` *(modify)* | Three new `JobType` members. `job.type` is `String(30)`, so no migration. |
| `app/worker/main.py` *(modify)* | Import the three new handler modules so they register. |
| `tests/test_series_metadata.py` *(create)* | Both provider shapes, and the absent-field cases. |
| `tests/test_status_write.py` *(create)* | Route validation and handler fan-out. |
| `tests/test_media_enrich.py` *(create)* | Enrichment parsing and cache staleness. |
| `tests/test_providers_parse.py` *(modify)* | The widened queries still parse older recorded fixtures. |
| `tests/test_api.py` *(modify)* | `GET /api/series/{id}` carries `metadata`. |

**Frontend**

| File | Responsibility |
|---|---|
| `src/ui/Tabs.tsx` *(create)* + `src/ui/index.ts` | A shared tab strip. Two screens will want it; it is not a series-detail private. |
| `src/lib/api.ts` *(modify)* | `SeriesMetadata` types and the three new calls. |
| `src/features/series/SeriesHeader.tsx` *(create)* | Breadcrumb, pills, title + native title, author credit, genre chips. |
| `src/features/series/ScoreStrip.tsx` *(create)* | Global score + vote count, personal rating, ranking, volumes. |
| `src/features/series/ProgressManager.tsx` *(create)* | Chapter stepper, list-status control, volumes read, dates, reread count, progress bar and the labelled estimate. |
| `src/features/series/SynopsisPanel.tsx` *(create)* | Synopsis and the official-metadata rows. |
| `src/features/series/SimilarWorks.tsx` *(create)* | Recommendations. |
| `src/features/series/CharacterGrid.tsx` *(create)* | Characters. |
| `src/features/series/NotesPanel.tsx` *(create)* | Private note and personal tags. |
| `src/features/series/SeriesDetailPage.tsx` *(modify)* | Composition only: the mockup's grid, and the tab strip over chapters / notes / characters. |
| `src/features/series/useSeriesDetail.ts` *(modify)* | `setListStatus` and `saveNotes`, both apply-then-confirm with rollback. |

---

## Task 1: Widen the AniList list query

**Files:**
- Modify: `backend/app/providers/anilist.py:75-97` (`LIST_QUERY`)
- Test: `backend/tests/test_providers_parse.py`
- Create: `backend/tests/fixtures/anilist_list_rich.json`

**Interfaces:**
- Consumes: nothing.
- Produces: `list_entry.raw` for AniList rows now carries `entry.score`, `entry.progressVolumes`, `entry.repeat`, `entry.notes`, `entry.startedAt`, `entry.completedAt`, `entry.updatedAt`, and under `entry.media`: `volumes`, `status`, `countryOfOrigin`, `popularity`, `favourites`, `siteUrl`, `bannerImage`, `endDate`, `startDate.month`, `startDate.day`, `tags`. Task 3 reads exactly these names.

Only cheap scalar fields go in the list query. `characters`, `recommendations`, `rankings` and `stats` are per-media object graphs; asking for them across a whole list is what Task 5 exists to avoid.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_providers_parse.py`:

```python
from app.providers.anilist import LIST_QUERY


def test_anilist_list_query_asks_for_every_field_the_detail_screen_reads():
    """The detail screen reads these out of `raw`; a trimmed query empties it
    silently, because a missing GraphQL field is simply absent from the
    response rather than an error."""
    for field in (
        "progressVolumes",
        "repeat",
        "notes",
        "startedAt",
        "completedAt",
        "volumes",
        "countryOfOrigin",
        "popularity",
        "favourites",
        "siteUrl",
        "endDate",
    ):
        assert field in LIST_QUERY, field


def test_anilist_keeps_the_whole_entry_as_raw(fixture):
    entry = parse_list(fixture("anilist_list_rich.json"))[0]
    assert entry.raw["media"]["volumes"] == 18
    assert entry.raw["media"]["countryOfOrigin"] == "JP"
    assert entry.raw["score"] == 9.5
    assert entry.raw["notes"] == "Reread chapter 120 before the anime."


def test_a_list_recorded_before_the_widened_query_still_parses(fixture):
    """Rows synced by the previous query have none of the new keys. The parser
    must not start depending on them."""
    entries = parse_list(fixture("anilist_list.json"))
    assert entries[0].raw["media"].get("volumes") is None
```

Create `backend/tests/fixtures/anilist_list_rich.json`:

```json
{
  "MediaListCollection": {
    "lists": [
      {
        "entries": [
          {
            "status": "CURRENT",
            "progress": 148,
            "progressVolumes": 16,
            "score": 9.5,
            "repeat": 0,
            "notes": "Reread chapter 120 before the anime.",
            "startedAt": { "year": 2024, "month": 1, "day": 12 },
            "completedAt": { "year": null, "month": null, "day": null },
            "updatedAt": 1729000000,
            "media": {
              "id": 119257,
              "chapters": 172,
              "volumes": 18,
              "synonyms": [],
              "description": "Taro Sakamoto was once the greatest hitman alive.",
              "genres": ["Action", "Comedy"],
              "averageScore": 91,
              "popularity": 54291,
              "favourites": 8123,
              "format": "MANGA",
              "status": "RELEASING",
              "countryOfOrigin": "JP",
              "siteUrl": "https://anilist.co/manga/119257",
              "bannerImage": null,
              "startDate": { "year": 2020, "month": 11, "day": 21 },
              "endDate": { "year": null, "month": null, "day": null },
              "title": {
                "romaji": "Sakamoto Days",
                "english": "Sakamoto Days",
                "native": "サカモトデイズ"
              },
              "coverImage": { "large": "https://example.invalid/cover.jpg" },
              "staff": {
                "edges": [
                  { "role": "Story & Art", "node": { "name": { "full": "Yuto Suzuki" } } }
                ]
              },
              "tags": [
                { "name": "Shounen", "rank": 92, "isGeneralSpoiler": false }
              ]
            }
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest \
  tests/test_providers_parse.py -k "detail_screen_reads or whole_entry_as_raw" -q
```

Expected: FAIL — `assert 'progressVolumes' in LIST_QUERY`.

- [ ] **Step 3: Widen the query**

Replace `LIST_QUERY` in `backend/app/providers/anilist.py`:

```python
# Every field below is read by the series detail screen out of `list_entry.raw`,
# which stores this entry verbatim. Only scalars and small objects belong here:
# `characters`, `recommendations`, `rankings` and `stats` are per-media graphs
# and are fetched one series at a time by the media_enrich job instead, because
# asking for them across a seven-hundred-entry list is one response AniList
# will not send twice.
LIST_QUERY = """
query ($userId: Int) {
  MediaListCollection(userId: $userId, type: MANGA) {
    lists {
      entries {
        status
        progress
        progressVolumes
        score(format: POINT_10_DECIMAL)
        repeat
        notes
        startedAt { year month day }
        completedAt { year month day }
        updatedAt
        media {
          id
          chapters
          volumes
          synonyms
          description(asHtml: false)
          genres
          averageScore
          popularity
          favourites
          format
          status
          countryOfOrigin
          siteUrl
          bannerImage
          startDate { year month day }
          endDate { year month day }
          title { romaji english native }
          coverImage { large }
          staff(perPage: 4) { edges { role node { name { full } } } }
          tags { name rank isGeneralSpoiler }
        }
      }
    }
  }
}
"""
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_providers_parse.py -q
.venv/bin/python -m ruff check app/ tests/
```

Expected: PASS, no lint findings.

- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/anilist.py backend/tests/test_providers_parse.py \
        backend/tests/fixtures/anilist_list_rich.json
git commit -m "feat(providers): read the AniList fields the detail screen shows

The screen had nothing to render because the list query never asked for
volumes, run dates, country or the viewer's own score and note. raw is JSONB
and stores the entry verbatim, so widening the query fills it on the next
sync with no migration."
```

---

## Task 2: Widen the MyAnimeList list fields

**Files:**
- Modify: `backend/app/providers/mal.py:29-32` (`LIST_FIELDS`)
- Test: `backend/tests/test_providers_parse.py`
- Create: `backend/tests/fixtures/mal_page_rich.json`

**Interfaces:**
- Consumes: nothing.
- Produces: `list_entry.raw` for MyAnimeList rows now carries, under `item.node`: `end_date`, `status`, `rank`, `popularity`, `num_list_users`, `num_scoring_users`, `num_volumes`, `serialization`, `background`; and under `item.list_status`: `score`, `num_volumes_read`, `is_rereading`, `start_date`, `finish_date`, `num_times_reread`, `tags`, `comments`, `updated_at`. Task 3 reads exactly these names.

`my_list_status` is a single field name in the request — the sub-keys arrive with it and are not listed individually. `serialization{name}` is the only source of the "SHUEISHA · WEEKLY SHŌNEN JUMP" breadcrumb in the mockup; AniList has no publisher at all.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_providers_parse.py`:

```python
from app.providers.mal import LIST_FIELDS


def test_mal_list_fields_ask_for_every_field_the_detail_screen_reads():
    for field in (
        "end_date",
        "rank",
        "num_scoring_users",
        "num_volumes",
        "serialization",
        "status",
    ):
        assert field in LIST_FIELDS, field


def test_mal_keeps_the_whole_item_as_raw(fixture):
    entry = parse_page(fixture("mal_page_rich.json"))[0]
    assert entry.raw["node"]["num_volumes"] == 18
    assert entry.raw["node"]["serialization"][0]["node"]["name"] == "Shounen Jump (Weekly)"
    assert entry.raw["list_status"]["num_times_reread"] == 0
    assert entry.raw["list_status"]["comments"] == "Reread chapter 120 before the anime."


def test_a_page_recorded_before_the_widened_fields_still_parses(fixture):
    entry = parse_page(fixture("mal_page.json"))[0]
    assert entry.raw["node"].get("num_volumes") is None
```

Create `backend/tests/fixtures/mal_page_rich.json`:

```json
{
  "data": [
    {
      "node": {
        "id": 121496,
        "title": "Sakamoto Days",
        "alternative_titles": { "en": "Sakamoto Days", "ja": "サカモトデイズ", "synonyms": [] },
        "main_picture": { "large": "https://example.invalid/cover.jpg" },
        "start_date": "2020-11-21",
        "end_date": null,
        "synopsis": "Taro Sakamoto was once the greatest hitman alive.",
        "mean": 9.07,
        "rank": 14,
        "popularity": 132,
        "num_list_users": 131334,
        "num_scoring_users": 54291,
        "media_type": "manga",
        "status": "currently_publishing",
        "genres": [{ "id": 1, "name": "Action" }, { "id": 4, "name": "Comedy" }],
        "num_volumes": 18,
        "num_chapters": 172,
        "authors": [
          { "node": { "first_name": "Yuto", "last_name": "Suzuki" }, "role": "Story & Art" }
        ],
        "serialization": [{ "node": { "name": "Shounen Jump (Weekly)" } }],
        "background": "",
        "my_list_status": {
          "status": "reading",
          "score": 10,
          "num_volumes_read": 16,
          "num_chapters_read": 148,
          "is_rereading": false,
          "start_date": "2024-01-12",
          "finish_date": null,
          "num_times_reread": 0,
          "tags": ["favourite"],
          "comments": "Reread chapter 120 before the anime.",
          "updated_at": "2024-10-18T14:32:00+00:00"
        }
      },
      "list_status": {
        "status": "reading",
        "score": 10,
        "num_volumes_read": 16,
        "num_chapters_read": 148,
        "is_rereading": false,
        "start_date": "2024-01-12",
        "finish_date": null,
        "num_times_reread": 0,
        "tags": ["favourite"],
        "comments": "Reread chapter 120 before the anime.",
        "updated_at": "2024-10-18T14:32:00+00:00"
      }
    }
  ],
  "paging": {}
}
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest \
  tests/test_providers_parse.py -k "mal_list_fields or whole_item_as_raw" -q
```

Expected: FAIL — `assert 'end_date' in LIST_FIELDS`.

- [ ] **Step 3: Widen the fields**

Replace `LIST_FIELDS` in `backend/app/providers/mal.py`:

```python
# The detail screen reads all of these out of `list_entry.raw`, which stores the
# item verbatim. `my_list_status` is one field name: its sub-keys (score,
# num_volumes_read, num_times_reread, tags, comments, dates) arrive with it and
# are not requested individually. `serialization{name}` is the only place either
# provider names the magazine a manga runs in.
LIST_FIELDS = (
    "list_status,alternative_titles,num_chapters,num_volumes,main_picture,title,"
    "synopsis,genres,start_date,end_date,status,authors{first_name,last_name},"
    "serialization{name},mean,rank,popularity,num_list_users,num_scoring_users,"
    "media_type,my_list_status,background"
)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_providers_parse.py -q
.venv/bin/python -m ruff check app/ tests/
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/mal.py backend/tests/test_providers_parse.py \
        backend/tests/fixtures/mal_page_rich.json
git commit -m "feat(providers): read the MyAnimeList fields the detail screen shows

serialization is the only field either provider carries that names the
magazine, and my_list_status brings the viewer's own score, note, tags and
reread count with it for the cost of one field name."
```

---

## Task 3: Normalise both provider shapes into one metadata block

**Files:**
- Create: `backend/app/api/series_metadata.py`
- Test: `backend/tests/test_series_metadata.py`

**Interfaces:**
- Consumes: the `raw` shapes Tasks 1 and 2 produce.
- Produces: `metadata_of(raws: list[dict[str, Any] | None], enrichment: dict[str, Any] | None = None) -> dict[str, Any]`, returning every key listed in the module docstring below. Task 4 calls it; Task 9 types its output in TypeScript.

A series can carry a `list_entry` from each provider, and the two do not overlap: only MyAnimeList names the magazine, only AniList reports the country of origin. One raw is therefore not enough — the function takes every raw the series has and the first provider that supplies a field wins.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_series_metadata.py`:

```python
"""One metadata block out of two provider vocabularies.

AniList nests the media under "media" and the viewer's own row at the top
level; MyAnimeList nests the media under "node" and the viewer's row under
"list_status". Neither is a superset of the other - `serialization` exists
only on MyAnimeList and `countryOfOrigin` only on AniList - so a series synced
from both must read both, and a series synced from one must not lose the
fields that one does report.
"""

from app.api.series_metadata import metadata_of

ANILIST_RAW = {
    "status": "CURRENT",
    "progress": 148,
    "progressVolumes": 16,
    "score": 9.5,
    "repeat": 0,
    "notes": "Reread chapter 120 before the anime.",
    "startedAt": {"year": 2024, "month": 1, "day": 12},
    "completedAt": {"year": None, "month": None, "day": None},
    "media": {
        "id": 119257,
        "chapters": 172,
        "volumes": 18,
        "description": "Taro Sakamoto was once the greatest hitman alive.",
        "genres": ["Action", "Comedy"],
        "averageScore": 91,
        "popularity": 54291,
        "favourites": 8123,
        "format": "MANGA",
        "status": "RELEASING",
        "countryOfOrigin": "JP",
        "siteUrl": "https://anilist.co/manga/119257",
        "startDate": {"year": 2020, "month": 11, "day": 21},
        "endDate": {"year": None, "month": None, "day": None},
        "title": {"romaji": "Sakamoto Days", "english": "Sakamoto Days", "native": "サカモトデイズ"},
        "staff": {"edges": [{"role": "Story & Art", "node": {"name": {"full": "Yuto Suzuki"}}}]},
        "tags": [{"name": "Shounen", "rank": 92, "isGeneralSpoiler": False}],
    },
}

MAL_RAW = {
    "node": {
        "id": 121496,
        "title": "Sakamoto Days",
        "alternative_titles": {"en": "Sakamoto Days", "ja": "サカモトデイズ"},
        "synopsis": "Taro Sakamoto was once the greatest hitman alive.",
        "mean": 9.07,
        "rank": 14,
        "num_scoring_users": 54291,
        "num_volumes": 18,
        "status": "currently_publishing",
        "start_date": "2020-11-21",
        "end_date": None,
        "genres": [{"id": 27, "name": "Shounen"}],
        "authors": [
            {"node": {"first_name": "Yuto", "last_name": "Suzuki"}, "role": "Story & Art"}
        ],
        "serialization": [{"node": {"name": "Shounen Jump (Weekly)"}}],
    },
    "list_status": {
        "status": "reading",
        "score": 10,
        "num_volumes_read": 16,
        "num_times_reread": 0,
        "start_date": "2024-01-12",
        "finish_date": None,
        "tags": ["favourite"],
        "comments": "Reread chapter 120 before the anime.",
        "updated_at": "2024-10-18T14:32:00+00:00",
    },
}


def test_anilist_alone_reports_what_only_anilist_has():
    meta = metadata_of([ANILIST_RAW])
    assert meta["native_title"] == "サカモトデイズ"
    assert meta["country"] == "JP"
    assert meta["publication_status"] == "releasing"
    assert meta["start_year"] == 2020
    assert meta["end_year"] is None
    assert meta["volumes_total"] == 18
    assert meta["volumes_read"] == 16
    assert meta["user_score"] == 9.5
    assert meta["credits"] == [{"role": "Story & Art", "name": "Yuto Suzuki"}]
    assert meta["demographic"] == "Shounen"
    assert meta["notes"] == "Reread chapter 120 before the anime."
    assert meta["started_at"] == "2024-01-12"
    assert meta["publisher"] is None


def test_mal_alone_reports_what_only_mal_has():
    meta = metadata_of([MAL_RAW])
    assert meta["publisher"] == "Shounen Jump (Weekly)"
    assert meta["rank"] == 14
    assert meta["vote_count"] == 54291
    assert meta["global_score"] == 9.1
    assert meta["user_score"] == 10.0
    assert meta["reread_count"] == 0
    assert meta["user_tags"] == ["favourite"]
    assert meta["country"] is None


def test_both_providers_merge_and_neither_field_is_lost():
    meta = metadata_of([ANILIST_RAW, MAL_RAW])
    assert meta["country"] == "JP"
    assert meta["publisher"] == "Shounen Jump (Weekly)"
    assert meta["rank"] == 14
    assert meta["providers"] == ["anilist", "mal"]


def test_the_first_raw_wins_a_field_both_providers_report():
    """Ordered by the caller (most recently updated entry first), so the
    fresher provider decides where the two disagree."""
    assert metadata_of([MAL_RAW, ANILIST_RAW])["global_score"] == 9.1
    assert metadata_of([ANILIST_RAW, MAL_RAW])["global_score"] == 9.1


def test_a_row_synced_before_the_widened_queries_reports_nulls_not_errors():
    thin = {"status": "CURRENT", "progress": 12, "media": {"genres": ["Action"]}}
    meta = metadata_of([thin])
    assert meta["volumes_total"] is None
    assert meta["credits"] == []
    assert meta["user_tags"] == []


def test_no_entries_at_all_is_an_empty_block_not_a_crash():
    meta = metadata_of([])
    assert meta["native_title"] is None
    assert meta["characters"] == []
    assert meta["similar"] == []


def test_enrichment_supplies_what_the_list_queries_cannot_carry():
    enrichment = {
        "rank": 14,
        "vote_count": 54291,
        "characters": [
            {"name": "Taro Sakamoto", "role": "MAIN", "image_url": "https://example.invalid/c.jpg"}
        ],
        "similar": [
            {
                "media_id": "105778",
                "title": "SPY x FAMILY",
                "cover_url": "https://example.invalid/s.jpg",
                "score": 8.9,
                "chapters": 104,
                "genres": ["Action", "Comedy"],
            }
        ],
    }
    meta = metadata_of([ANILIST_RAW], enrichment)
    assert meta["rank"] == 14
    assert meta["vote_count"] == 54291
    assert meta["characters"][0]["name"] == "Taro Sakamoto"
    assert meta["similar"][0]["title"] == "SPY x FAMILY"


def test_a_field_the_entries_already_carry_beats_a_stale_enrichment():
    meta = metadata_of([MAL_RAW], {"rank": 900})
    assert meta["rank"] == 14
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_series_metadata.py -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.api.series_metadata'`.

- [ ] **Step 3: Write the module**

Create `backend/app/api/series_metadata.py`:

```python
"""Everything the detail screen shows that is not a column of its own.

`list_entry.raw` stores the provider's payload verbatim, so widening a list
query fills this in with no migration - but the two providers describe a manga
in different vocabularies, and neither is a superset of the other. Only
MyAnimeList names the magazine a series runs in; only AniList reports its
country of origin. A series synced from both must read both, so this takes
every raw the series has rather than the newest one, and the first provider
that supplies a field wins.

Nothing here invents a value. A field no provider returned comes back None,
and the screen is expected to render the absence rather than a placeholder.
"""

from typing import Any

# The demographic the mockup shows as its own pill. MyAnimeList files these as
# genres; AniList files them as tags. Matching against a closed set is what
# keeps "Action" out of the slot.
DEMOGRAPHICS = ("Shounen", "Shoujo", "Seinen", "Josei", "Kids")

# AniList's vocabulary and MyAnimeList's, onto one.
PUBLICATION_STATUS = {
    "RELEASING": "releasing",
    "FINISHED": "finished",
    "NOT_YET_RELEASED": "not_yet_released",
    "CANCELLED": "cancelled",
    "HIATUS": "hiatus",
    "currently_publishing": "releasing",
    "finished": "finished",
    "not_yet_published": "not_yet_released",
    "discontinued": "cancelled",
    "on_hiatus": "hiatus",
}

FIELDS = (
    "native_title",
    "synopsis",
    "publisher",
    "publication_status",
    "start_year",
    "end_year",
    "country",
    "demographic",
    "site_url",
    "global_score",
    "vote_count",
    "rank",
    "popularity",
    "favourites",
    "user_score",
    "volumes_total",
    "volumes_read",
    "reread_count",
    "started_at",
    "completed_at",
    "list_updated_at",
    "notes",
)


def metadata_of(
    raws: list[dict[str, Any] | None],
    enrichment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Every raw the series has, newest first. The first to answer wins."""
    blocks = [_block_of(raw) for raw in raws if raw]
    merged: dict[str, Any] = {field: None for field in FIELDS}
    for field in FIELDS:
        for block in blocks:
            if block.get(field) is not None:
                merged[field] = block[field]
                break

    # Lists concatenate rather than compete: two providers credit the same
    # author under differently spelled roles, and dropping one of the two
    # would drop the artist credit for anyone synced to both.
    merged["credits"] = _unique(
        [credit for block in blocks for credit in block["credits"]],
        key=lambda credit: (credit["role"].lower(), credit["name"].lower()),
    )
    merged["user_tags"] = _unique(
        [tag for block in blocks for tag in block["user_tags"]], key=str.lower
    )
    merged["providers"] = sorted({block["provider"] for block in blocks if block["provider"]})

    enrichment = enrichment or {}
    for field in ("rank", "vote_count", "popularity", "favourites"):
        # An entry that already carries the field beats the cache, which can be
        # weeks old; the cache exists for what no list query can carry.
        if merged.get(field) is None and enrichment.get(field) is not None:
            merged[field] = enrichment[field]
    merged["characters"] = list(enrichment.get("characters") or [])
    merged["similar"] = list(enrichment.get("similar") or [])
    merged["enriched_at"] = enrichment.get("fetched_at")
    return merged


def _block_of(raw: dict[str, Any]) -> dict[str, Any]:
    if "node" in raw:
        return _from_mal(raw)
    if "media" in raw:
        return _from_anilist(raw)
    # Neither wrapper: a hand-built fixture, or a row flattened by an older
    # code path. Read it as AniList's shape with an empty media object, which
    # yields an all-None block rather than a KeyError.
    return _from_anilist({"media": raw})


def _from_anilist(raw: dict[str, Any]) -> dict[str, Any]:
    media = raw.get("media") or {}
    title = media.get("title") or {}
    tags = [t.get("name") for t in media.get("tags") or [] if isinstance(t, dict)]
    return {
        "provider": "anilist",
        "native_title": title.get("native"),
        "synopsis": media.get("description"),
        "publisher": None,  # AniList carries no publisher or magazine at all.
        "publication_status": PUBLICATION_STATUS.get(media.get("status") or ""),
        "start_year": (media.get("startDate") or {}).get("year"),
        "end_year": (media.get("endDate") or {}).get("year"),
        "country": media.get("countryOfOrigin"),
        "demographic": _demographic([*(media.get("genres") or []), *tags]),
        "site_url": media.get("siteUrl"),
        # averageScore is 0-100; the screen renders one ten-point scale, so a
        # 91 next to MyAnimeList's 9.07 reads as the same opinion.
        "global_score": _tenths(media.get("averageScore"), divisor=10),
        # AniList publishes no vote count on Media; it comes from
        # stats.scoreDistribution, which only the enrichment job fetches.
        "vote_count": None,
        "rank": None,  # rankings is a per-media graph; enrichment fetches it.
        "popularity": media.get("popularity"),
        "favourites": media.get("favourites"),
        "user_score": _tenths(raw.get("score"), divisor=1),
        "volumes_total": media.get("volumes"),
        "volumes_read": raw.get("progressVolumes"),
        "reread_count": raw.get("repeat"),
        "started_at": _fuzzy_date(raw.get("startedAt")),
        "completed_at": _fuzzy_date(raw.get("completedAt")),
        "list_updated_at": None,  # AniList's updatedAt is a unix int, not an ISO string.
        "notes": raw.get("notes") or None,
        "credits": [
            {"role": edge.get("role") or "Staff", "name": (edge.get("node") or {}).get("name", {}).get("full")}
            for edge in (media.get("staff") or {}).get("edges") or []
            if (edge.get("node") or {}).get("name", {}).get("full")
        ],
        "user_tags": [],  # AniList has customLists, not free tags.
    }


def _from_mal(raw: dict[str, Any]) -> dict[str, Any]:
    node = raw.get("node") or {}
    status = raw.get("list_status") or node.get("my_list_status") or {}
    alt = node.get("alternative_titles") or {}
    genres = [g.get("name") for g in node.get("genres") or [] if isinstance(g, dict)]
    serialization = node.get("serialization") or []
    return {
        "provider": "mal",
        "native_title": alt.get("ja"),
        "synopsis": node.get("synopsis"),
        "publisher": ((serialization[0] or {}).get("node") or {}).get("name") if serialization else None,
        "publication_status": PUBLICATION_STATUS.get(node.get("status") or ""),
        "start_year": _year(node.get("start_date")),
        "end_year": _year(node.get("end_date")),
        "country": None,  # MyAnimeList does not report one.
        "demographic": _demographic(genres),
        "site_url": f"https://myanimelist.net/manga/{node['id']}" if node.get("id") else None,
        "global_score": _tenths(node.get("mean"), divisor=1),
        "vote_count": node.get("num_scoring_users"),
        "rank": node.get("rank"),
        "popularity": node.get("num_list_users"),
        "favourites": None,
        "user_score": _tenths(status.get("score"), divisor=1),
        "volumes_total": node.get("num_volumes") or None,
        "volumes_read": status.get("num_volumes_read"),
        "reread_count": status.get("num_times_reread"),
        "started_at": status.get("start_date"),
        "completed_at": status.get("finish_date"),
        "list_updated_at": status.get("updated_at"),
        "notes": status.get("comments") or None,
        "credits": [
            {
                "role": author.get("role") or "Staff",
                "name": " ".join(
                    part
                    for part in (
                        (author.get("node") or {}).get("first_name"),
                        (author.get("node") or {}).get("last_name"),
                    )
                    if part
                ),
            }
            for author in node.get("authors") or []
            if (author.get("node") or {}).get("first_name")
            or (author.get("node") or {}).get("last_name")
        ],
        "user_tags": [tag for tag in status.get("tags") or [] if tag],
    }


def _demographic(names: list[str | None]) -> str | None:
    for name in names:
        if name in DEMOGRAPHICS:
            return name
    return None


def _tenths(value: Any, *, divisor: int) -> float | None:
    """One ten-point scale, one decimal. A zero score is "unrated" on both
    providers, not a genuine nought, and is reported as absent."""
    if value in (None, 0):
        return None
    return round(float(value) / divisor, 1)


def _year(date: str | None) -> int | None:
    """MyAnimeList dates are "YYYY", "YYYY-MM" or "YYYY-MM-DD"."""
    if not date:
        return None
    head = date.split("-")[0]
    return int(head) if head.isdigit() else None


def _fuzzy_date(date: dict[str, Any] | None) -> str | None:
    """AniList's FuzzyDate, as an ISO date. Any part may be null, and a date
    with no year is no date at all."""
    date = date or {}
    year = date.get("year")
    if not year:
        return None
    month, day = date.get("month"), date.get("day")
    if month and day:
        return f"{year:04d}-{month:02d}-{day:02d}"
    if month:
        return f"{year:04d}-{month:02d}"
    return f"{year:04d}"


def _unique(items: list[Any], key: Any) -> list[Any]:
    seen: set[Any] = set()
    result: list[Any] = []
    for item in items:
        marker = key(item)
        if marker not in seen:
            seen.add(marker)
            result.append(item)
    return result
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_series_metadata.py -q
.venv/bin/python -m ruff check app/ tests/
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/series_metadata.py backend/tests/test_series_metadata.py
git commit -m "feat(api): normalise both providers into one metadata block

Neither provider is a superset of the other - only MyAnimeList names the
magazine, only AniList the country - so the block reads every entry a series
has instead of the newest one, and a field nobody returned stays null rather
than being filled in."
```

---

## Task 4: Serve the metadata block from the detail endpoint

**Files:**
- Modify: `backend/app/api/routes_series.py:206-256` (`series_detail`)
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: `metadata_of(raws, enrichment)` from Task 3.
- Produces: `GET /api/series/{id}` answers `{series, metadata, mapping, chapters, entries}`. Task 9 types `metadata`.

The list route is deliberately left alone: the library grid renders none of this, and a metadata block per card would be paid for on every library load.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_api.py`:

```python
async def test_series_detail_carries_the_metadata_block(client):
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta)
                values ('Sakamoto Days', 'sakamoto-days', false, '{}'::jsonb)
                """
            )
        )
        await session.execute(
            text(
                """
                insert into list_entry
                       (provider, provider_media_id, series_id, status,
                        user_progress_chapter, synonyms, raw)
                values ('mal', '121496', 1, 'reading', 148, '[]'::jsonb, :raw)
                """
            ),
            {
                "raw": json.dumps(
                    {
                        "node": {
                            "id": 121496,
                            "mean": 9.07,
                            "rank": 14,
                            "num_scoring_users": 54291,
                            "num_volumes": 18,
                            "status": "currently_publishing",
                            "start_date": "2020-11-21",
                            "serialization": [{"node": {"name": "Shounen Jump (Weekly)"}}],
                            "alternative_titles": {"ja": "サカモトデイズ"},
                        },
                        "list_status": {"status": "reading", "score": 10},
                    }
                )
            },
        )
        await session.commit()

    body = (await client.get("/api/series/1")).json()
    assert body["metadata"]["publisher"] == "Shounen Jump (Weekly)"
    assert body["metadata"]["native_title"] == "サカモトデイズ"
    assert body["metadata"]["rank"] == 14
    assert body["metadata"]["characters"] == []


async def test_series_detail_with_no_list_entry_still_carries_an_empty_block(client):
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta)
                values ('Orphan', 'orphan', false, '{}'::jsonb)
                """
            )
        )
        await session.commit()

    body = (await client.get("/api/series/1")).json()
    assert body["metadata"]["publisher"] is None
    assert body["metadata"]["providers"] == []
```

Add `import json` to the test module's imports if it is not already there.

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest \
  tests/test_api.py -k metadata_block -q
```

Expected: FAIL — `KeyError: 'metadata'`.

- [ ] **Step 3: Wire it in**

In `backend/app/api/routes_series.py`, add the import beside the others:

```python
from app.api.series_metadata import metadata_of
```

Replace the `entries` query and the return statement inside `series_detail`:

```python
    entries = await session.execute(
        text(
            """
            select provider, provider_media_id, status, user_progress_chapter,
                   updated_at, raw
              from list_entry
             where series_id = :id
             order by updated_at desc nulls last, provider
            """
        ),
        {"id": series_id},
    )
    # Newest first, because metadata_of resolves a field both providers report
    # in favour of the first raw that answers.
    entry_rows = entries.all()

    return {
        "series": _row_to_series(row),
        "metadata": metadata_of(
            [entry.raw for entry in entry_rows],
            (row.meta or {}).get("enrichment"),
        ),
        "mapping": {"source_site": row.source_site, "source_url": row.source_url}
        if row.source_url
        else None,
        "chapters": [
            {
                "number": float(c.number),
                "title": c.title,
                "state": c.state,
                "file_path": c.file_path,
            }
            for c in chapters.all()
        ],
        "entries": [
            {
                "provider": e.provider,
                "provider_media_id": e.provider_media_id,
                "status": e.status,
                "user_progress_chapter": e.user_progress_chapter,
                "updated_at": e.updated_at.isoformat() if e.updated_at else None,
            }
            for e in entry_rows
        ],
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_api.py -q
.venv/bin/python -m ruff check app/ tests/
```

Expected: PASS, including the pre-existing `test_series_detail_returns_chapters_and_entries`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes_series.py backend/tests/test_api.py
git commit -m "feat(api): return the metadata block with a series detail

The library grid renders none of it, so the list route is left alone rather
than paying for a block per card on every library load."
```

---

## Task 5: Fetch the per-media extras AniList will not send for a whole list

**Files:**
- Modify: `backend/app/providers/anilist.py` (add `MEDIA_DETAIL_QUERY`, `parse_media_detail`, `AniListSource.fetch_media_detail`)
- Test: `backend/tests/test_media_enrich.py`
- Create: `backend/tests/fixtures/anilist_media_detail.json`

**Interfaces:**
- Consumes: nothing.
- Produces: `parse_media_detail(data: dict) -> dict` returning `{"rank", "vote_count", "characters", "similar"}`; `AniListSource.fetch_media_detail(access_token: str, media_id: str) -> dict` returning the same. Task 6's handler calls the latter and stores the result under `series.meta['enrichment']`.

The query was run against `https://graphql.anilist.co` on 2026-09-14 and its exact response shape is the fixture below. `rank` is taken from the `RATED`+`allTime` ranking, which is the one the mockup's "RANKING GERAL" means. AniList publishes no vote count field — the sum of `stats.scoreDistribution[].amount` is the number of scores cast, and that is what the count is.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_media_enrich.py`:

```python
"""The per-media graph AniList will not send across a whole list.

Characters, recommendations, rankings and the score distribution are object
graphs per media. Asking for them inside the list query means one response
carrying seven hundred of each, which AniList rate-limits away. They are
fetched one series at a time instead, and cached on the series.
"""

from app.providers.anilist import parse_media_detail


def test_the_rank_is_the_all_time_rated_one(fixture):
    detail = parse_media_detail(fixture("anilist_media_detail.json"))
    # Four rankings come back: rated/popular, all-time and per-year. "Ranking
    # geral" is the all-time rated one; the per-year rank is a different claim.
    assert detail["rank"] == 54


def test_the_vote_count_is_the_score_distribution_summed(fixture):
    detail = parse_media_detail(fixture("anilist_media_detail.json"))
    assert detail["vote_count"] == 33400


def test_characters_keep_their_role_and_portrait(fixture):
    first = parse_media_detail(fixture("anilist_media_detail.json"))["characters"][0]
    assert first == {
        "name": "Taro Sakamoto",
        "role": "MAIN",
        "image_url": "https://example.invalid/char.png",
    }


def test_similar_works_carry_what_the_card_renders(fixture):
    first = parse_media_detail(fixture("anilist_media_detail.json"))["similar"][0]
    assert first == {
        "media_id": "105398",
        "title": "Solo Leveling",
        "cover_url": "https://example.invalid/solo.jpg",
        "score": 8.4,
        "chapters": 179,
        "genres": ["Action", "Adventure"],
    }


def test_a_media_that_answers_with_nothing_is_empty_not_an_error():
    assert parse_media_detail({"Media": None}) == {
        "rank": None,
        "vote_count": None,
        "characters": [],
        "similar": [],
    }
```

Create `backend/tests/fixtures/anilist_media_detail.json`:

```json
{
  "Media": {
    "rankings": [
      { "rank": 54, "type": "RATED", "allTime": true, "context": "highest rated all time", "year": null },
      { "rank": 16, "type": "POPULAR", "allTime": true, "context": "most popular all time", "year": null },
      { "rank": 5, "type": "RATED", "allTime": false, "context": "highest rated", "year": 2020 }
    ],
    "stats": {
      "scoreDistribution": [
        { "score": 10, "amount": 185 },
        { "score": 20, "amount": 106 },
        { "score": 30, "amount": 162 },
        { "score": 40, "amount": 209 },
        { "score": 50, "amount": 525 },
        { "score": 60, "amount": 847 },
        { "score": 70, "amount": 2800 },
        { "score": 80, "amount": 5975 },
        { "score": 90, "amount": 11289 },
        { "score": 100, "amount": 11302 }
      ]
    },
    "characters": {
      "edges": [
        {
          "role": "MAIN",
          "node": {
            "id": 180887,
            "name": { "full": "Taro Sakamoto" },
            "image": { "large": "https://example.invalid/char.png" }
          }
        }
      ]
    },
    "recommendations": {
      "nodes": [
        {
          "mediaRecommendation": {
            "id": 105398,
            "title": { "romaji": "Na Honjaman Level Up", "english": "Solo Leveling" },
            "coverImage": { "large": "https://example.invalid/solo.jpg" },
            "averageScore": 84,
            "chapters": 179,
            "genres": ["Action", "Adventure"],
            "format": "MANHWA"
          }
        },
        { "mediaRecommendation": null }
      ]
    }
  }
}
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_media_enrich.py -q
```

Expected: FAIL — `ImportError: cannot import name 'parse_media_detail'`.

- [ ] **Step 3: Add the query, the parser and the client method**

In `backend/app/providers/anilist.py`, beside `LIST_QUERY`:

```python
# Run against https://graphql.anilist.co on 2026-09-14; the recorded response is
# tests/fixtures/anilist_media_detail.json. Everything here is a per-media object
# graph, which is why none of it belongs in LIST_QUERY: one list response
# carrying these for seven hundred entries is a response AniList declines to
# send twice.
MEDIA_DETAIL_QUERY = """
query ($id: Int) {
  Media(id: $id, type: MANGA) {
    rankings { rank type allTime context year }
    stats { scoreDistribution { score amount } }
    characters(perPage: 12, sort: [ROLE, RELEVANCE]) {
      edges { role node { id name { full } image { large } } }
    }
    recommendations(perPage: 6, sort: RATING_DESC) {
      nodes {
        mediaRecommendation {
          id
          title { romaji english }
          coverImage { large }
          averageScore
          chapters
          genres
          format
        }
      }
    }
  }
}
"""
```

Beside `parse_list`:

```python
def parse_media_detail(data: dict[str, Any]) -> dict[str, Any]:
    """Pure parser, so the shape can be tested from the recorded response."""
    media = data.get("Media") or {}
    rankings = media.get("rankings") or []
    rank = next(
        (
            r.get("rank")
            for r in rankings
            if r.get("type") == "RATED" and r.get("allTime")
        ),
        None,
    )
    # AniList publishes no vote count. The score distribution is one bucket per
    # ten points carrying how many people voted it, so the sum is the count.
    distribution = (media.get("stats") or {}).get("scoreDistribution") or []
    votes = sum(int(bucket.get("amount") or 0) for bucket in distribution)
    return {
        "rank": rank,
        "vote_count": votes or None,
        "characters": [
            {
                "name": (edge.get("node") or {}).get("name", {}).get("full"),
                "role": edge.get("role"),
                "image_url": ((edge.get("node") or {}).get("image") or {}).get("large"),
            }
            for edge in (media.get("characters") or {}).get("edges") or []
            if (edge.get("node") or {}).get("name", {}).get("full")
        ],
        "similar": [
            {
                "media_id": str(node["id"]),
                "title": (node.get("title") or {}).get("english")
                or (node.get("title") or {}).get("romaji"),
                "cover_url": (node.get("coverImage") or {}).get("large"),
                "score": round(node["averageScore"] / 10, 1)
                if node.get("averageScore") is not None
                else None,
                "chapters": node.get("chapters"),
                "genres": [g for g in node.get("genres") or [] if isinstance(g, str)],
            }
            # A recommendation whose target was deleted comes back as a null
            # node rather than being omitted.
            for node in (
                item.get("mediaRecommendation")
                for item in (media.get("recommendations") or {}).get("nodes") or []
            )
            if node and node.get("id")
        ],
    }
```

On `AniListSource`, beside `fetch_list`:

```python
    async def fetch_media_detail(self, access_token: str, media_id: str) -> dict[str, Any]:
        data = await self._post(access_token, MEDIA_DETAIL_QUERY, {"id": int(media_id)})
        return parse_media_detail(data)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_media_enrich.py -q
.venv/bin/python -m ruff check app/ tests/
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/anilist.py backend/tests/test_media_enrich.py \
        backend/tests/fixtures/anilist_media_detail.json
git commit -m "feat(providers): fetch one manga's rankings, characters and recommendations

These are per-media object graphs. Asking for them inside the list query is a
response AniList rate-limits away, so they are fetched one series at a time."
```

---

## Task 6: Cache the enrichment on the series

**Files:**
- Modify: `backend/app/enums.py` (`JobType.MEDIA_ENRICH`)
- Create: `backend/app/handlers/media_enrich.py`
- Modify: `backend/app/worker/main.py` (import the new handler)
- Modify: `backend/app/api/routes_series.py` (`series_detail` enqueues when the cache is cold)
- Test: `backend/tests/test_media_enrich.py`

**Interfaces:**
- Consumes: `AniListSource.fetch_media_detail` from Task 5; `metadata_of`'s `enrichment` argument from Task 3.
- Produces: `series.meta['enrichment'] = {rank, vote_count, characters, similar, fetched_at}`. `ENRICHMENT_MAX_AGE_DAYS = 14`. `is_stale(enrichment: dict | None, now: datetime) -> bool`.

`job.type` is a `String(30)` column with no database enum behind it, so a new `JobType` member needs no migration. Verify that in Step 4 by queueing one against the real database.

**`app/worker/main.py` must import the handler.** A handler that is never imported never runs its `@register` decorator, and the job fails with `no handler registered` — a build problem wearing a code problem's clothes.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_media_enrich.py`:

```python
from datetime import UTC, datetime, timedelta

from app.handlers.media_enrich import ENRICHMENT_MAX_AGE_DAYS, is_stale


def test_an_absent_cache_is_stale():
    assert is_stale(None, datetime.now(UTC)) is True


def test_a_cache_with_no_timestamp_is_stale():
    assert is_stale({"rank": 14}, datetime.now(UTC)) is True


def test_a_fresh_cache_is_not_refetched():
    now = datetime.now(UTC)
    fresh = {"fetched_at": (now - timedelta(days=1)).isoformat()}
    assert is_stale(fresh, now) is False


def test_a_cache_past_the_window_is_refetched():
    now = datetime.now(UTC)
    old = {"fetched_at": (now - timedelta(days=ENRICHMENT_MAX_AGE_DAYS + 1)).isoformat()}
    assert is_stale(old, now) is True
```

Add to `backend/tests/test_api.py`:

```python
async def test_opening_a_detail_with_a_cold_cache_queues_the_enrichment(client):
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta)
                values ('Sakamoto Days', 'sakamoto-days', false, '{}'::jsonb)
                """
            )
        )
        await session.execute(
            text(
                """
                insert into list_entry
                       (provider, provider_media_id, series_id, status,
                        user_progress_chapter, synonyms, raw)
                values ('anilist', '119257', 1, 'reading', 148, '[]'::jsonb, '{}'::jsonb)
                """
            )
        )
        await session.commit()

    await client.get("/api/series/1")

    async with get_sessionmaker()() as session:
        queued = await session.execute(
            text("select type, payload from job where series_id = 1")
        )
        rows = queued.all()
    assert [row.type for row in rows] == ["media_enrich"]
    assert rows[0].payload["series_id"] == 1


async def test_a_warm_cache_queues_nothing(client):
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta)
                values ('Sakamoto Days', 'sakamoto-days', false, :meta)
                """
            ),
            {"meta": json.dumps({"enrichment": {"fetched_at": datetime.now(UTC).isoformat()}})},
        )
        await session.commit()

    await client.get("/api/series/1")

    async with get_sessionmaker()() as session:
        queued = await session.execute(text("select count(*) from job"))
    assert queued.scalar_one() == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest \
  tests/test_media_enrich.py tests/test_api.py -k "stale or enrichment or cold_cache or warm_cache" -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.handlers.media_enrich'`.

- [ ] **Step 3: Write the handler and the enqueue**

In `backend/app/enums.py`, add to `JobType`:

```python
    MEDIA_ENRICH = "media_enrich"
```

Create `backend/app/handlers/media_enrich.py`:

```python
"""The per-media extras, cached on the series that needed them.

The list queries cannot carry characters, recommendations, rankings or a score
distribution - they are object graphs per media, and one list response holding
them for every entry is a response AniList declines to send. They are fetched
one series at a time instead, by this job, and kept on `series.meta` so that
opening a detail page twice costs one request rather than two.

Only AniList answers this: MyAnimeList has no characters for manga at all, and
everything else it reports already arrives with the list fields.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text

from app.enums import JobType, Provider
from app.handlers.base import JobContext, PermanentError, register
from app.providers import get_source
from app.providers.tokens import NotConnected, access_token_for

# Rankings and recommendations move over months, not hours. Two weeks is short
# enough that a climbing series is not stuck at a stale rank forever, and long
# enough that browsing the library does not spend the rate limit.
ENRICHMENT_MAX_AGE_DAYS = 14


def is_stale(enrichment: dict[str, Any] | None, now: datetime) -> bool:
    """A cache with no timestamp is stale: it predates this field and there is
    no way to tell how old it is."""
    stamp = (enrichment or {}).get("fetched_at")
    if not stamp:
        return True
    try:
        fetched = datetime.fromisoformat(stamp)
    except ValueError:
        return True
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=UTC)
    return now - fetched > timedelta(days=ENRICHMENT_MAX_AGE_DAYS)


@register(JobType.MEDIA_ENRICH)
async def handle(ctx: JobContext) -> None:
    series_id = int(ctx.payload["series_id"])
    result = await ctx.session.execute(
        text(
            """
            select provider_media_id
              from list_entry
             where series_id = :series_id and provider = :provider
             limit 1
            """
        ),
        {"series_id": series_id, "provider": str(Provider.ANILIST)},
    )
    media_id = result.scalar_one_or_none()
    if media_id is None:
        # Nothing to ask, and asking again later will not change that.
        raise PermanentError(f"series {series_id} has no AniList entry to enrich")

    try:
        token = await access_token_for(ctx.session, Provider.ANILIST)
    except NotConnected as failure:
        raise PermanentError(str(failure)) from failure

    detail = await get_source(Provider.ANILIST).fetch_media_detail(token, media_id)
    detail["fetched_at"] = datetime.now(UTC).isoformat()

    await ctx.session.execute(
        text(
            """
            update series
               set meta = jsonb_set(
                       coalesce(meta, '{}'::jsonb), '{enrichment}', :detail::jsonb, true
                   )
             where id = :series_id
            """
        ),
        {"series_id": series_id, "detail": json.dumps(detail)},
    )
    await ctx.log(f"enriched series {series_id} from AniList media {media_id}")
```

Add `import json` at the top of that module.

In `backend/app/worker/main.py`, add `media_enrich` to the handler import block.

In `backend/app/api/routes_series.py`, inside `series_detail`, immediately before the `return`:

```python
    # Opening the page is what asks for the extras. A job rather than a fetch
    # in the request path: AniList rate-limits, and a detail page must not fail
    # to render because a third party was slow.
    enrichment = (row.meta or {}).get("enrichment")
    if is_stale(enrichment, datetime.now(UTC)) and any(
        entry.provider == str(Provider.ANILIST) for entry in entry_rows
    ):
        await repo.enqueue(
            session,
            JobType.MEDIA_ENRICH,
            {"series_id": series_id},
            priority=50,
            series_id=series_id,
            dedupe_key=f"media_enrich:{series_id}",
        )
        await session.commit()
```

with these imports added to the route module:

```python
from datetime import UTC, datetime

from app.enums import JobType, Provider
from app.handlers.media_enrich import is_stale
```

and `enrichment` passed to `metadata_of` in place of the inline lookup added in Task 4.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests -q
.venv/bin/python -m ruff check app/ tests/
```

Expected: PASS. The `media_enrich` job inserted by `test_opening_a_detail_with_a_cold_cache_queues_the_enrichment` is the proof that `job.type` needed no migration.

- [ ] **Step 5: Commit**

```bash
git add backend/app/enums.py backend/app/handlers/media_enrich.py \
        backend/app/worker/main.py backend/app/api/routes_series.py \
        backend/tests/test_media_enrich.py backend/tests/test_api.py
git commit -m "feat(queue): cache a series' rankings, characters and recommendations

Opening the detail page queues the fetch rather than making it: AniList rate
limits, and the page must not fail to render because a third party was slow.
Two weeks of cache is short enough that a climbing rank unsticks and long
enough that browsing does not spend the limit."
```

---

## Task 7: Change a series' list status from the detail screen

**Files:**
- Modify: `backend/app/enums.py` (`JobType.STATUS_WRITE`)
- Create: `backend/app/handlers/status_write.py`
- Modify: `backend/app/worker/main.py`
- Modify: `backend/app/api/routes_series.py` (`POST /{series_id}/status`)
- Test: `backend/tests/test_status_write.py`

**Interfaces:**
- Consumes: `Source.set_status(access_token, media_id, status)`, which both providers already implement.
- Produces: `POST /api/series/{id}/status` with body `{"status": "reading"}` answering `{"ok": true, "status": "reading", "queued": true}`. Task 9 calls it; Task 11 renders the control.

The mockup's "Status na Biblioteca: Lendo / Pausa / Completo" is this. It is the same shape `progress_write` uses — validate in the route so the screen learns of a refusal immediately, dedupe the job on the series so a double click cannot race, fan out in the handler to every connected provider.

Writing a status never carries progress. That rule is why this is its own job rather than a branch inside `progress_write`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_status_write.py`:

```python
"""A list status the user set by hand, pushed to every list that holds it."""

import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                "truncate job, job_event, series, list_entry, provider_token "
                "restart identity cascade"
            )
        )
        await session.commit()
    yield


async def seed() -> None:
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta)
                values ('Eleceed', 'eleceed', false, '{}'::jsonb)
                """
            )
        )
        await session.execute(
            text(
                """
                insert into list_entry
                       (provider, provider_media_id, series_id, status,
                        user_progress_chapter, synonyms, raw)
                values ('mal', '7', 1, 'reading', 280, '[]'::jsonb, '{}'::jsonb)
                """
            )
        )
        await session.commit()


async def test_a_status_the_vocabulary_does_not_hold_is_refused(client):
    await seed()
    response = await client.post("/api/series/1/status", json={"status": "borrowed"})
    assert response.status_code == 422


async def test_a_status_for_a_missing_series_is_a_404(client):
    response = await client.post("/api/series/999/status", json={"status": "reading"})
    assert response.status_code == 404
    assert response.json() == {"detail": "series not found"}


async def test_a_series_on_no_list_cannot_have_a_status_written(client):
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta)
                values ('Orphan', 'orphan', false, '{}'::jsonb)
                """
            )
        )
        await session.commit()
    response = await client.post("/api/series/1/status", json={"status": "completed"})
    assert response.status_code == 409
    assert response.json() == {"detail": "this series is not on any reading list"}


async def test_a_status_change_queues_one_job(client):
    await seed()
    body = (await client.post("/api/series/1/status", json={"status": "completed"})).json()
    assert body == {"ok": True, "status": "completed", "queued": True}

    async with get_sessionmaker()() as session:
        rows = (await session.execute(text("select type, payload from job"))).all()
    assert [row.type for row in rows] == ["status_write"]
    assert rows[0].payload == {"series_id": 1, "status": "completed"}


async def test_a_second_click_raises_the_queued_job_rather_than_adding_one(client):
    await seed()
    await client.post("/api/series/1/status", json={"status": "completed"})
    await client.post("/api/series/1/status", json={"status": "on_hold"})

    async with get_sessionmaker()() as session:
        rows = (await session.execute(text("select payload from job"))).all()
    # One job per series, carrying what the user last asked for. Two jobs is how
    # a status the user moved away from reaches their real account second.
    assert len(rows) == 1
    assert rows[0].payload["status"] == "on_hold"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_status_write.py -q
```

Expected: FAIL — all four POSTs answer 405, because the route does not exist.

- [ ] **Step 3: Write the handler and the route**

In `backend/app/enums.py`, add to `JobType`:

```python
    STATUS_WRITE = "status_write"
```

Create `backend/app/handlers/status_write.py`:

```python
"""A list status the user set on the detail screen, pushed to every list.

Separate from PROGRESS_WRITE because the product brief's rule is that a status
write never carries progress, and two jobs cannot blur into one the way two
branches of one job can. Separate from LIST_WRITE because that one is scoped to
a suggestion being approved, not to a series already in the library.

Writing a status is idempotent, which is what makes a retry free.
"""

from sqlalchemy import text

from app.enums import JobType, ListStatus, Provider
from app.handlers.base import JobContext, PermanentError, register
from app.providers import get_source
from app.providers.tokens import NotConnected, access_token_for


@register(JobType.STATUS_WRITE)
async def handle(ctx: JobContext) -> None:
    series_id = int(ctx.payload["series_id"])
    status = ListStatus(ctx.payload["status"])

    # A left join, so an entry whose provider has no stored token is still seen:
    # joining it away would let the job report success while never attempting
    # half of the user's lists.
    result = await ctx.session.execute(
        text(
            """
            select e.id, e.provider, e.provider_media_id,
                   t.provider is not null as connected
              from list_entry e
              left join provider_token t on t.provider = e.provider
             where e.series_id = :series_id
            """
        ),
        {"series_id": series_id},
    )
    entries = result.all()
    if not any(entry.connected for entry in entries):
        raise PermanentError(f"series {series_id} has no connected list entry")

    written = 0
    for entry in entries:
        if not entry.connected:
            await ctx.log(f"{entry.provider} is not connected; skipped", level="warning")
            continue
        try:
            token = await access_token_for(ctx.session, Provider(entry.provider))
        except NotConnected as failure:
            await ctx.log(f"{entry.provider}: {failure}", level="warning")
            continue
        await get_source(Provider(entry.provider)).set_status(
            token, entry.provider_media_id, status
        )
        # The local row follows the write, not the click: a status that never
        # reached the provider must not read as synced on the next page load.
        await ctx.session.execute(
            text("update list_entry set status = :status where id = :id"),
            {"status": str(status), "id": entry.id},
        )
        written += 1
        await ctx.log(f"{entry.provider} set to {status}")

    if written == 0:
        raise PermanentError(f"series {series_id}: no list accepted the status")
```

In `backend/app/worker/main.py`, add `status_write` to the handler import block.

In `backend/app/api/routes_series.py`, add the body model beside the others:

```python
class StatusIn(BaseModel):
    status: ListStatus
```

with `from app.enums import JobType, ListStatus, Provider` at the top, and the route:

```python
@router.post("/{series_id}/status")
async def set_list_status(series_id: int, body: StatusIn, session: Session) -> dict[str, Any]:
    """Validated here as well as in the handler, so the screen learns of a
    refusal on the click rather than from a job that failed minutes later."""
    exists = await session.execute(
        text("select 1 from series where id = :id"), {"id": series_id}
    )
    if exists.first() is None:
        raise HTTPException(status_code=404, detail="series not found")

    entries = await session.execute(
        text("select count(*) from list_entry where series_id = :id"), {"id": series_id}
    )
    if entries.scalar_one() == 0:
        raise HTTPException(
            status_code=409, detail="this series is not on any reading list"
        )

    await repo.enqueue(
        session,
        JobType.STATUS_WRITE,
        {"series_id": series_id, "status": str(body.status)},
        priority=0,
        series_id=series_id,
        dedupe_key=f"status_write:{series_id}",
    )
    # One job per series, carrying the status last asked for. A second click
    # while the first is queued raises that job rather than adding one, or the
    # status the user moved away from lands on their account second.
    await session.execute(
        text(
            """
            update job
               set payload = jsonb_set(payload, '{status}', to_jsonb(:status::text))
             where type = :type and series_id = :series_id and state = 'pending'
            """
        ),
        {"status": str(body.status), "type": str(JobType.STATUS_WRITE), "series_id": series_id},
    )
    await session.commit()
    return {"ok": True, "status": str(body.status), "queued": True}
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests -q
.venv/bin/python -m ruff check app/ tests/
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/enums.py backend/app/handlers/status_write.py \
        backend/app/worker/main.py backend/app/api/routes_series.py \
        backend/tests/test_status_write.py
git commit -m "feat(api): set a series' list status from the detail screen

Its own job, not a branch of progress_write: a status write never carries
progress, and one job per series means a second click raises the queued job
instead of racing it."
```

---

## Task 8: Save the private note and personal tags

**Files:**
- Modify: `backend/app/providers/base.py` (`Source.set_notes`)
- Modify: `backend/app/providers/anilist.py` (`NOTES_MUTATION`, `set_notes`)
- Modify: `backend/app/providers/mal.py` (`set_notes`)
- Modify: `backend/app/enums.py` (`JobType.NOTES_WRITE`)
- Create: `backend/app/handlers/notes_write.py`
- Modify: `backend/app/worker/main.py`
- Modify: `backend/app/api/routes_series.py` (`POST /{series_id}/notes`)
- Test: `backend/tests/test_notes_write.py`

**Interfaces:**
- Consumes: `access_token_for`, `get_source`.
- Produces: `Source.set_notes(access_token: str, media_id: str, notes: str, tags: list[str]) -> None`; `POST /api/series/{id}/notes` with body `{"notes": "...", "tags": ["..."]}` answering `{"ok": true, "queued": true}`. Task 9 calls it; Task 13 renders the panel.

The mockup's "Notas Privadas do Usuário" and "Tags Pessoais" are AniList's `MediaList.notes` and MyAnimeList's `my_list_status.comments` / `my_list_status.tags`. AniList has no free-tag field — `customLists` is a different thing — so tags are written only where they exist, and the panel says so.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_notes_write.py`:

```python
"""The note the user keeps on a series, written where each provider keeps one.

AniList calls it MediaList.notes and has no free tags; MyAnimeList calls it
my_list_status.comments and does have tags. A provider that holds neither is
skipped rather than failing the job for the providers that do.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker
from app.providers.anilist import NOTES_MUTATION

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                "truncate job, job_event, series, list_entry, provider_token "
                "restart identity cascade"
            )
        )
        await session.commit()
    yield


def test_the_anilist_mutation_writes_notes_and_nothing_else():
    """Sending progress or status alongside would overwrite what the user set
    elsewhere with whatever this screen happened to be holding."""
    assert "notes: $notes" in NOTES_MUTATION
    assert "progress" not in NOTES_MUTATION
    assert "status" not in NOTES_MUTATION


async def test_a_note_for_a_missing_series_is_a_404(client):
    response = await client.post("/api/series/999/notes", json={"notes": "x", "tags": []})
    assert response.status_code == 404


async def test_saving_a_note_queues_one_job(client):
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta)
                values ('Eleceed', 'eleceed', false, '{}'::jsonb)
                """
            )
        )
        await session.execute(
            text(
                """
                insert into list_entry
                       (provider, provider_media_id, series_id, status,
                        user_progress_chapter, synonyms, raw)
                values ('mal', '7', 1, 'reading', 280, '[]'::jsonb, '{}'::jsonb)
                """
            )
        )
        await session.commit()

    body = (
        await client.post(
            "/api/series/1/notes", json={"notes": "Reread 120 first.", "tags": ["favourite"]}
        )
    ).json()
    assert body == {"ok": True, "queued": True}

    async with get_sessionmaker()() as session:
        rows = (await session.execute(text("select type, payload from job"))).all()
    assert [row.type for row in rows] == ["notes_write"]
    assert rows[0].payload["notes"] == "Reread 120 first."
    assert rows[0].payload["tags"] == ["favourite"]


async def test_a_note_longer_than_a_provider_accepts_is_refused(client):
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta)
                values ('Eleceed', 'eleceed', false, '{}'::jsonb)
                """
            )
        )
        await session.commit()
    response = await client.post(
        "/api/series/1/notes", json={"notes": "x" * 5001, "tags": []}
    )
    assert response.status_code == 422
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_notes_write.py -q
```

Expected: FAIL — `ImportError: cannot import name 'NOTES_MUTATION'`.

- [ ] **Step 3: Write the provider methods, the handler and the route**

In `backend/app/providers/base.py`, beside `set_status`:

```python
    async def set_notes(
        self, access_token: str, media_id: str, notes: str, tags: list[str]
    ) -> None:
        """Write the user's private note. Not every provider keeps one."""
        raise NotSupported(f"{self.provider} keeps no private note")
```

In `backend/app/providers/anilist.py`, beside the other mutations:

```python
# Notes alone. SaveMediaListEntry writes whatever fields it is handed, so
# sending progress or status alongside would overwrite what the user set on
# their own account with whatever this screen was holding at the time.
NOTES_MUTATION = """
mutation ($mediaId: Int, $notes: String) {
  SaveMediaListEntry(mediaId: $mediaId, notes: $notes) { id notes }
}
"""
```

and on `AniListSource`:

```python
    async def set_notes(
        self, access_token: str, media_id: str, notes: str, tags: list[str]
    ) -> None:
        # AniList has no free-tag field on a list entry - customLists are named
        # lists, not tags - so tags are dropped here rather than approximated.
        await self._post(access_token, NOTES_MUTATION, {"mediaId": int(media_id), "notes": notes})
```

On `MyAnimeListSource` in `backend/app/providers/mal.py`:

```python
    async def set_notes(
        self, access_token: str, media_id: str, notes: str, tags: list[str]
    ) -> None:
        headers = {"Authorization": f"Bearer {access_token}"}
        # The field is form-encoded and comma-separated, as the whole
        # my_list_status PATCH body is.
        data = {"comments": notes, "tags": ",".join(tags)}
        url = f"{API_BASE}/manga/{media_id}/my_list_status"
        if self._client is not None:
            response = await self._client.patch(url, data=data, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.patch(url, data=data, headers=headers)
        response.raise_for_status()
```

In `backend/app/enums.py`, add to `JobType`:

```python
    NOTES_WRITE = "notes_write"
```

Create `backend/app/handlers/notes_write.py`:

```python
"""The user's own note on a series, written wherever a provider keeps one.

AniList calls it MediaList.notes; MyAnimeList calls it my_list_status.comments
and also has free tags, which AniList does not. A provider that keeps neither
is skipped, not failed - one provider without the field must not stop the note
reaching the one that has it.
"""

from sqlalchemy import text

from app.enums import JobType, Provider
from app.handlers.base import JobContext, PermanentError, register
from app.providers import get_source
from app.providers.base import NotSupported
from app.providers.tokens import NotConnected, access_token_for


@register(JobType.NOTES_WRITE)
async def handle(ctx: JobContext) -> None:
    series_id = int(ctx.payload["series_id"])
    notes = str(ctx.payload.get("notes") or "")
    tags = [str(tag) for tag in ctx.payload.get("tags") or []]

    result = await ctx.session.execute(
        text(
            """
            select e.provider, e.provider_media_id,
                   t.provider is not null as connected
              from list_entry e
              left join provider_token t on t.provider = e.provider
             where e.series_id = :series_id
            """
        ),
        {"series_id": series_id},
    )
    entries = result.all()
    if not any(entry.connected for entry in entries):
        raise PermanentError(f"series {series_id} has no connected list entry")

    written = 0
    for entry in entries:
        if not entry.connected:
            continue
        try:
            token = await access_token_for(ctx.session, Provider(entry.provider))
        except NotConnected as failure:
            await ctx.log(f"{entry.provider}: {failure}", level="warning")
            continue
        try:
            await get_source(Provider(entry.provider)).set_notes(
                token, entry.provider_media_id, notes, tags
            )
        except NotSupported as failure:
            await ctx.log(str(failure), level="warning")
            continue
        written += 1
        await ctx.log(f"note written to {entry.provider}")

    if written == 0:
        raise PermanentError(f"series {series_id}: no list keeps a note")
```

In `backend/app/worker/main.py`, add `notes_write` to the handler import block.

In `backend/app/api/routes_series.py`:

```python
class NotesIn(BaseModel):
    # MyAnimeList refuses a comment past 5000 characters, and refuses it again
    # however many times it is asked - so the refusal belongs here, where the
    # user can still edit what they typed.
    notes: str = Field(max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=20)


@router.post("/{series_id}/notes")
async def save_notes(series_id: int, body: NotesIn, session: Session) -> dict[str, Any]:
    exists = await session.execute(
        text("select 1 from series where id = :id"), {"id": series_id}
    )
    if exists.first() is None:
        raise HTTPException(status_code=404, detail="series not found")

    await repo.enqueue(
        session,
        JobType.NOTES_WRITE,
        {"series_id": series_id, "notes": body.notes, "tags": body.tags},
        priority=0,
        series_id=series_id,
        dedupe_key=f"notes_write:{series_id}",
    )
    await session.execute(
        text(
            """
            update job
               set payload = :payload::jsonb
             where type = :type and series_id = :series_id and state = 'pending'
            """
        ),
        {
            "payload": json.dumps(
                {"series_id": series_id, "notes": body.notes, "tags": body.tags}
            ),
            "type": str(JobType.NOTES_WRITE),
            "series_id": series_id,
        },
    )
    await session.commit()
    return {"ok": True, "queued": True}
```

with `import json` and `from pydantic import BaseModel, Field` at the top of the route module.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests -q
.venv/bin/python -m ruff check app/ tests/
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/base.py backend/app/providers/anilist.py \
        backend/app/providers/mal.py backend/app/enums.py \
        backend/app/handlers/notes_write.py backend/app/worker/main.py \
        backend/app/api/routes_series.py backend/tests/test_notes_write.py
git commit -m "feat(api): save a series' private note to every list that keeps one

The AniList mutation carries notes and nothing else: SaveMediaListEntry writes
whatever it is handed, and sending progress alongside would overwrite what the
user set on their own account with whatever this screen was holding."
```

---

## A note on frontend verification

There is no test runner in `frontend/` — `package.json` has `dev`, `build` and `preview` and nothing else, and adding a runner is not in this plan's scope. Every frontend task is therefore verified three ways, and all three are required:

1. `npm run build` — this runs `tsc -b` first, so a type error fails the build.
2. `grep -r "<class>" dist/` — a Tailwind class is only real if the built CSS contains it. Three classes on the redesign branch typechecked, built clean and generated nothing: a name built by string interpolation (the scanner never sees it), `font-label-md` (the scale exists only under `fontSize`, so `text-label-md` already carries size *and* weight), and `bg-secondary/12` (the opacity modifier takes scale steps; 12 needs `/[0.12]`). The source is what lies; the build output is what tells the truth.
3. Exercising the screen in the running stack against a real series.

---

## Task 9: Type the metadata block and add the shared tab strip

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/ui/Tabs.tsx`
- Modify: `frontend/src/ui/index.ts`

**Interfaces:**
- Consumes: the payload Tasks 4, 6, 7 and 8 produce.
- Produces: `SeriesMetadata`, `SeriesCredit`, `SeriesCharacter`, `SimilarWork`; `SeriesDetail.metadata`; `api.setListStatus(id, status)`, `api.saveNotes(id, notes, tags)`; `<Tabs options value onChange />`. Tasks 10-14 use all of them.

`Tabs` goes in `ui/`, not in the series feature folder: the unmatched detail panel in the companion plan wants the same strip, and feature folders never import from each other.

- [ ] **Step 1: Add the types and the calls**

In `frontend/src/lib/api.ts`, beside the other interfaces:

```typescript
export interface SeriesCredit {
  role: string
  name: string
}

export interface SeriesCharacter {
  name: string
  role: string | null
  image_url: string | null
}

export interface SimilarWork {
  media_id: string
  title: string | null
  cover_url: string | null
  score: number | null
  chapters: number | null
  genres: string[]
}

/**
 * Everything the detail screen shows that is not a column of its own. Every
 * field is nullable because neither provider is a superset of the other: only
 * MyAnimeList names the magazine a series runs in, only AniList reports its
 * country of origin, and a series synced before those fields were requested
 * reports neither. A null here is rendered as an absence, never as a zero.
 */
export interface SeriesMetadata {
  native_title: string | null
  synopsis: string | null
  publisher: string | null
  publication_status:
    | 'releasing'
    | 'finished'
    | 'not_yet_released'
    | 'cancelled'
    | 'hiatus'
    | null
  start_year: number | null
  end_year: number | null
  country: string | null
  demographic: string | null
  site_url: string | null
  global_score: number | null
  vote_count: number | null
  rank: number | null
  popularity: number | null
  favourites: number | null
  user_score: number | null
  volumes_total: number | null
  volumes_read: number | null
  reread_count: number | null
  started_at: string | null
  completed_at: string | null
  list_updated_at: string | null
  notes: string | null
  user_tags: string[]
  credits: SeriesCredit[]
  characters: SeriesCharacter[]
  similar: SimilarWork[]
  providers: string[]
  enriched_at: string | null
}
```

Add `metadata` to `SeriesDetail`:

```typescript
export interface SeriesDetail {
  series: Series
  metadata: SeriesMetadata
  mapping: { source_site: string; source_url: string } | null
  chapters: SeriesChapter[]
  entries: SeriesEntry[]
}
```

Add to the `api` object:

```typescript
  setListStatus: (id: number, status: ListStatus) =>
    request<{ ok: boolean; status: ListStatus; queued: boolean }>(
      `/api/series/${id}/status`,
      { method: 'POST', body: JSON.stringify({ status }) },
    ),
  saveNotes: (id: number, notes: string, tags: string[]) =>
    request<{ ok: boolean; queued: boolean }>(`/api/series/${id}/notes`, {
      method: 'POST',
      body: JSON.stringify({ notes, tags }),
    }),
```

- [ ] **Step 2: Write the tab strip**

Create `frontend/src/ui/Tabs.tsx`:

```tsx
// The tab strip over "Capítulos & Histórico (172) / Minhas Notas / Personagens"
// in the detail mockup. It lives in ui/ rather than the series folder because
// the unmatched detail panel wants the same strip, and feature folders never
// import from each other.
export function Tabs<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string; count?: number | null }[]
  value: T
  onChange: (value: T) => void
}) {
  return (
    <div
      role="tablist"
      className="flex flex-wrap items-center gap-space-xs border-b border-outline-variant"
    >
      {options.map((option) => {
        const selected = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={selected}
            onClick={() => onChange(option.value)}
            className={`-mb-px rounded-t-lg border-b-2 px-space-md py-space-sm text-label-md transition-colors ${
              selected
                ? 'border-primary text-on-surface'
                : 'border-transparent text-outline hover:text-on-surface'
            }`}
          >
            {option.label}
            {/* A count only when the API served one. A tab reading "(0)" where
                the number is simply unknown is the invented-figure problem in
                miniature. */}
            {option.count != null && (
              <span className="ml-space-xs font-mono text-label-sm text-outline">
                ({option.count})
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
```

Add to `frontend/src/ui/index.ts`, in alphabetical position:

```typescript
export { Tabs } from './Tabs'
```

- [ ] **Step 3: Verify the build and the classes**

```bash
cd frontend
npm run build
grep -r "border-outline-variant" dist/ | head -1
grep -r "rounded-t-lg" dist/ | head -1
```

Expected: the build succeeds and both greps print a match. A grep that prints nothing means the class generated no rule — fix it before committing.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/ui/Tabs.tsx frontend/src/ui/index.ts
git commit -m "feat(web): type the series metadata block and add a tab strip

Every field is nullable because neither provider is a superset of the other,
and a null renders as an absence rather than a zero."
```

---

## Task 10: The hero header and the score strip

**Files:**
- Create: `frontend/src/features/series/SeriesHeader.tsx`
- Create: `frontend/src/features/series/ScoreStrip.tsx`

**Interfaces:**
- Consumes: `SeriesMetadata`, `Series` from Task 9.
- Produces: `<SeriesHeader series={Series} metadata={SeriesMetadata} />` and `<ScoreStrip metadata={SeriesMetadata} />`. Task 14 composes both.

The mockup's header carries, left to right: a publisher breadcrumb, a row of pills (publication status, run years, demographic, country), the title with its native spelling beside it, the author credit, and the genre chips. Every one of those is now served. The mockup's "Salvar / Compartilhar" pair is not: nothing in this product saves or shares a series, and a button that does nothing is worse than no button.

- [ ] **Step 1: Write the header**

Create `frontend/src/features/series/SeriesHeader.tsx`:

```tsx
import { Badge, StatusPill } from '../../ui'
import type { Series, SeriesMetadata } from '../../lib/api'
import { formatSeriesFormat } from '../../lib/format'

const PUBLICATION_LABEL: Record<string, string> = {
  releasing: 'Publishing',
  finished: 'Finished',
  not_yet_released: 'Not yet published',
  cancelled: 'Cancelled',
  hiatus: 'On hiatus',
}

/** "2020 — present", "2015 — 2021", or "2020" when only one year is known. */
function runYears(start: number | null, end: number | null): string | null {
  if (!start) return null
  if (!end) return `${start} — present`
  if (end === start) return `${start}`
  return `${start} — ${end}`
}

export function SeriesHeader({
  series,
  metadata,
}: {
  series: Series
  metadata: SeriesMetadata
}) {
  const format = formatSeriesFormat(series.format)
  const years = runYears(metadata.start_year, metadata.end_year)
  const credits = metadata.credits.slice(0, 3)

  return (
    <div className="flex min-w-0 flex-col gap-space-sm lg:col-span-9">
      {/* Only MyAnimeList names the magazine. A series synced from AniList
          alone has no breadcrumb, and the row is absent rather than empty. */}
      {metadata.publisher && (
        <p className="font-mono text-label-sm uppercase tracking-wide text-outline">
          {metadata.publisher}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {metadata.publication_status && (
          <Badge tone="secondary">{PUBLICATION_LABEL[metadata.publication_status]}</Badge>
        )}
        {years && <Badge tone="tertiary">{years}</Badge>}
        {metadata.demographic && <Badge tone="primary">{metadata.demographic}</Badge>}
        {metadata.country && (
          <span className="rounded bg-surface-container-high px-2 py-0.5 font-mono text-label-sm text-on-surface-variant">
            {metadata.country}
          </span>
        )}
        {format && <Badge tone="tertiary">{format}</Badge>}
        {series.status && <StatusPill status={series.status} />}
        {series.state === 'needs_review' && <Badge tone="error">Needs review</Badge>}
        {series.auto_download && <Badge tone="secondary">Auto-download active</Badge>}
      </div>

      {/* display-lg already carries weight 800 and -0.03em tracking, so a paired
          font-extrabold/tracking-tight would only fight it. */}
      <h1 className="flex flex-wrap items-baseline gap-space-md text-display-lg text-on-surface">
        {series.title}
        {metadata.native_title && metadata.native_title !== series.title && (
          <span className="text-headline-md text-on-surface-variant">
            {metadata.native_title}
          </span>
        )}
      </h1>

      {credits.length > 0 && (
        <p className="text-body-md text-on-surface-variant">
          {credits.map((credit, index) => (
            <span key={`${credit.role}-${credit.name}`}>
              {index > 0 && ' · '}
              {credit.role} by{' '}
              <span className="font-semibold text-on-surface">{credit.name}</span>
            </span>
          ))}
        </p>
      )}

      {series.genres.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {series.genres.map((genre) => (
            <span
              key={genre}
              className="rounded bg-surface-container-high px-2 py-0.5 font-mono text-label-sm text-on-surface-variant"
            >
              {genre}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Write the score strip**

Create `frontend/src/features/series/ScoreStrip.tsx`:

```tsx
import { Card } from '../../ui'
import type { SeriesMetadata } from '../../lib/api'

/** "54,291" — thousands separated, because a six-figure vote count run
 * together is unreadable at label size. */
function grouped(value: number): string {
  return value.toLocaleString('en-GB')
}

function Cell({
  label,
  value,
  detail,
  tone = 'text-on-surface',
}: {
  label: string
  value: string
  detail?: string | null
  tone?: string
}) {
  return (
    <div className="flex flex-col gap-space-xs">
      <span className="font-mono text-label-sm uppercase tracking-wide text-outline">
        {label}
      </span>
      <span className={`text-headline-md ${tone}`}>{value}</span>
      {detail && <span className="font-mono text-label-sm text-outline">{detail}</span>}
    </div>
  )
}

/**
 * The mockup's four-cell strip: global score, personal rating, cadence and
 * ranking. Cadence is dropped — neither provider reports a manga's release
 * schedule, and it would be the one invented figure on the screen. Volumes
 * take the empty cell, and they are served.
 *
 * A cell whose value no provider returned is not rendered. The strip disappears
 * entirely when none of the four is known.
 */
export function ScoreStrip({ metadata }: { metadata: SeriesMetadata }) {
  const cells = [
    metadata.global_score != null && (
      <Cell
        key="global"
        label="Global score"
        value={`★ ${metadata.global_score.toFixed(2)}`}
        detail={metadata.vote_count != null ? `${grouped(metadata.vote_count)} votes` : null}
        tone="text-tertiary"
      />
    ),
    metadata.user_score != null && (
      <Cell key="mine" label="My rating" value={`${metadata.user_score.toFixed(1)} / 10`} />
    ),
    metadata.volumes_total != null && (
      <Cell
        key="volumes"
        label="Volumes"
        value={`${metadata.volumes_read ?? 0} / ${metadata.volumes_total}`}
        detail="read"
      />
    ),
    metadata.rank != null && (
      <Cell key="rank" label="Overall ranking" value={`#${metadata.rank}`} />
    ),
  ].filter(Boolean)

  if (cells.length === 0) return null

  return (
    <Card as="section" elevated className="grid grid-cols-2 gap-space-lg md:grid-cols-4">
      {cells}
    </Card>
  )
}
```

- [ ] **Step 3: Verify the build and the classes**

```bash
cd frontend
npm run build
grep -r "uppercase" dist/ | head -1
grep -r "md:grid-cols-4" dist/ | head -1
```

Expected: build succeeds, both greps match.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/series/SeriesHeader.tsx \
        frontend/src/features/series/ScoreStrip.tsx
git commit -m "feat(web): render the series header and score strip

The mockup's release-cadence cell is dropped: neither provider reports a
manga's schedule, and it would have been the one invented figure on the page.
Volumes take the slot, and both providers serve them."
```

---

## Task 11: The quick progress manager

**Files:**
- Move: `frontend/src/features/library/useIncrementFlash.ts` → `frontend/src/ui/useIncrementFlash.ts`
- Modify: `frontend/src/features/library/QuickIncrement.tsx`, `frontend/src/features/library/SeriesTable.tsx` (import path)
- Create: `frontend/src/features/series/ProgressManager.tsx`
- Modify: `frontend/src/features/series/useSeriesDetail.ts`

**Interfaces:**
- Consumes: `api.setProgress`, `api.setListStatus` from Task 9.
- Produces: `useSeriesDetail` additionally returns `setProgress(next: number): Promise<void>` and `setListStatus(status: ListStatus): Promise<void>`; `<ProgressManager detail={SeriesDetail} total={number | null} onProgress onStatus />`. Task 14 composes it.

`useIncrementFlash` becomes a second screen's dependency here, so it moves to `ui/` — `ui/`, not `lib/`, because the branch building the Home screen in parallel is moving it to exactly that path, and two destinations for one file is a merge conflict nobody needs to have. Feature folders never import from each other, and this is no longer a small duplicated helper — it is the await-then-flash contract two screens both need.

The mockup's panel also carries "Ajustar Datas & Metas" and a chapters-per-day goal. Goals are stored nowhere and are dropped; the dates beside them (started, last updated, reread count) are served and are shown.

- [ ] **Step 1: Move the hook**

```bash
cd frontend
git mv src/features/library/useIncrementFlash.ts src/ui/useIncrementFlash.ts
```

Update the import in `src/features/library/QuickIncrement.tsx`:

```typescript
import { useIncrementFlash, type FlashState } from '../../ui/useIncrementFlash'
```

and the matching import in `src/features/library/SeriesTable.tsx`. Change the hook's own docstring first line to name both screens:

```typescript
/**
 * Shared by every control that calls `increment` — the library grid's glass
 * overlay, the table's inline stepper and the detail screen's progress
 * manager. A second copy of it is how one of them quietly lost the rejection
 * flash, which is why it lives in ui/ rather than in a feature folder.
 */
```

- [ ] **Step 2: Extend the detail hook**

In `frontend/src/features/series/useSeriesDetail.ts`, add beside `toggleAutoDownload`:

```typescript
  // Apply, then confirm — the same rollback-on-rejection shape
  // toggleAutoDownload uses, so a refused write visibly reverts instead of
  // leaving the screen showing a number the server never accepted.
  const setProgress = useCallback(
    async (next: number) => {
      let previous: SeriesDetail | null = null
      setData((current) => {
        previous = current
        return current
          ? { ...current, series: { ...current.series, progress: next } }
          : current
      })
      try {
        await api.setProgress(id, next)
      } catch (failure) {
        if (previous) setData(previous)
        throw failure
      }
    },
    [id, setData],
  )

  const setListStatus = useCallback(
    async (status: ListStatus) => {
      let previous: SeriesDetail | null = null
      setData((current) => {
        previous = current
        return current
          ? { ...current, series: { ...current.series, status } }
          : current
      })
      try {
        await api.setListStatus(id, status)
      } catch (failure) {
        if (previous) setData(previous)
        throw failure
      }
    },
    [id, setData],
  )
```

Add `ListStatus` to the imports (`import type { ListStatus } from '../../lib/format'`) and return both from the hook.

- [ ] **Step 3: Write the panel**

Create `frontend/src/features/series/ProgressManager.tsx`:

```tsx
import { Card, Icon, ProgressBar, SegmentedControl } from '../../ui'
import type { ListStatus } from '../../lib/format'
import type { SeriesDetail } from '../../lib/api'
import { formatChapter, relativeTime } from '../../lib/format'
import { useIncrementFlash } from '../../ui/useIncrementFlash'

// The three the mockup's own control offers. The full vocabulary has five;
// plan-to-read and dropped are set on the provider, not from a reading screen.
const STATUS_OPTIONS: { value: ListStatus; label: string }[] = [
  { value: 'reading', label: 'Reading' },
  { value: 'on_hold', label: 'Paused' },
  { value: 'completed', label: 'Completed' },
]

/** A date as the user's locale writes it, or nothing when no date was given. */
function onDay(iso: string | null): string | null {
  if (!iso) return null
  const parsed = new Date(iso)
  return Number.isNaN(parsed.getTime()) ? iso : parsed.toLocaleDateString('en-GB')
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-space-sm">
      <span className="font-mono text-label-sm text-outline">{label}</span>
      <span className="font-mono text-label-md text-on-surface">{value}</span>
    </div>
  )
}

export function ProgressManager({
  detail,
  total,
  minutesPerChapter,
  onProgress,
  onStatus,
}: {
  detail: SeriesDetail
  total: number | null
  /** `reading_minutes_per_chapter` from settings. The remaining-time figure is
   * derived from it and is labelled an estimate, because it is one. */
  minutesPerChapter: number | null
  onProgress: (next: number) => Promise<void>
  onStatus: (status: ListStatus) => Promise<void>
}) {
  const { series, metadata } = detail
  const { busy, trigger } = useIncrementFlash(onProgress)
  const remaining = total != null ? Math.max(total - series.progress, 0) : null
  const estimate =
    remaining != null && minutesPerChapter != null ? remaining * minutesPerChapter : null

  return (
    <Card as="section" elevated className="flex flex-col gap-space-lg">
      <div className="flex flex-wrap items-center justify-between gap-space-md">
        <h2 className="text-headline-sm text-on-surface">Progress</h2>
        {series.status && (
          <SegmentedControl
            options={STATUS_OPTIONS}
            value={series.status}
            onChange={(status) => {
              void onStatus(status)
            }}
          />
        )}
      </div>

      <div className="grid grid-cols-1 gap-space-lg md:grid-cols-2">
        <div className="flex flex-col gap-space-sm">
          <span className="font-mono text-label-sm uppercase tracking-wide text-outline">
            Chapters read
          </span>
          <div className="flex items-center gap-space-sm">
            <button
              type="button"
              disabled={busy || series.progress <= 0}
              onClick={() => void trigger(series.progress - 1)}
              aria-label="Step back one chapter"
              className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface-container-high text-on-surface transition-colors hover:bg-surface-bright disabled:cursor-not-allowed disabled:text-outline"
            >
              <Icon name="chevron" className="h-4 w-4 rotate-90" />
            </button>
            <span className="min-w-16 text-center text-headline-lg text-on-surface">
              {formatChapter(series.progress)}
            </span>
            <button
              type="button"
              disabled={busy}
              onClick={() => void trigger(series.progress + 1)}
              aria-label="Mark next chapter read"
              className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-on-primary transition-colors hover:bg-primary-container disabled:cursor-not-allowed"
            >
              <Icon name="add" className="h-4 w-4" />
            </button>
            {total != null && (
              <span className="font-mono text-label-md text-outline">/ {total}</span>
            )}
          </div>
          {total != null && (
            <ProgressBar value={series.progress} max={total} tone="secondary" />
          )}
          {remaining != null && (
            <p className="font-mono text-label-sm text-outline">
              {remaining} chapters left
              {/* Labelled an estimate because it is derived from a setting,
                  not measured. A number presented as measured when it was
                  assumed is worse than no number. */}
              {estimate != null && <> · about {Math.round(estimate / 60)}h estimated</>}
            </p>
          )}
        </div>

        <div className="flex flex-col gap-space-xs">
          {metadata.volumes_total != null && (
            <Row
              label="Volumes"
              value={`${metadata.volumes_read ?? 0} of ${metadata.volumes_total}`}
            />
          )}
          {onDay(metadata.started_at) && <Row label="Started" value={onDay(metadata.started_at)!} />}
          {onDay(metadata.completed_at) && (
            <Row label="Finished" value={onDay(metadata.completed_at)!} />
          )}
          {metadata.list_updated_at && (
            <Row label="Last updated" value={relativeTime(metadata.list_updated_at)} />
          )}
          {metadata.reread_count != null && (
            <Row label="Rereads" value={`${metadata.reread_count}`} />
          )}
        </div>
      </div>
    </Card>
  )
}
```

- [ ] **Step 4: Verify the build and the classes**

```bash
cd frontend
npm run build
grep -r "min-w-16" dist/ | head -1
grep -r "rotate-90" dist/ | head -1
```

Expected: build succeeds, both greps match. `min-w-16` is not a default Tailwind class in every version — if the grep is empty, replace it with a spacing token from `tailwind.config.ts` rather than a literal.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/ui/useIncrementFlash.ts frontend/src/features/library/QuickIncrement.tsx \
        frontend/src/features/library/SeriesTable.tsx \
        frontend/src/features/series/ProgressManager.tsx \
        frontend/src/features/series/useSeriesDetail.ts
git commit -m "feat(web): manage reading progress and list status from the detail screen

useIncrementFlash moves to ui/ now that a second screen needs it: feature
folders never import from each other, and this is the await-then-flash
contract both screens share rather than a helper worth duplicating.

The mockup's reading goal is dropped - nothing stores one - and the remaining
time is labelled an estimate, because it is derived from a setting."
```

---

## Task 12: Synopsis, similar works and characters

**Files:**
- Create: `frontend/src/features/series/SynopsisPanel.tsx`
- Create: `frontend/src/features/series/SimilarWorks.tsx`
- Create: `frontend/src/features/series/CharacterGrid.tsx`

**Interfaces:**
- Consumes: `SeriesMetadata`, `SimilarWork`, `SeriesCharacter` from Task 9.
- Produces: `<SynopsisPanel metadata={SeriesMetadata} />`, `<SimilarWorks items={SimilarWork[]} />`, `<CharacterGrid characters={SeriesCharacter[]} />`. Task 14 composes them.

AniList returns its description with HTML break tags in it. It is rendered as text, never as markup: `dangerouslySetInnerHTML` over a third party's string is an injection the moment AniList's sanitiser slips.

- [ ] **Step 1: Write the synopsis panel**

Create `frontend/src/features/series/SynopsisPanel.tsx`:

```tsx
import { Card } from '../../ui'
import type { SeriesMetadata } from '../../lib/api'

/**
 * AniList returns its description with `<br>` and `<i>` in it. Rendering it as
 * markup would mean trusting a third party's sanitiser with our DOM, so the
 * tags are stripped and the paragraphs are split on the breaks they marked.
 */
function paragraphs(synopsis: string): string[] {
  return synopsis
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .split(/\n{2,}|\n/)
    .map((line) => line.trim())
    .filter(Boolean)
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-space-sm">
      <span className="font-mono text-label-sm text-outline">{label}</span>
      <span className="font-mono text-label-md text-on-surface">{value}</span>
    </div>
  )
}

export function SynopsisPanel({ metadata }: { metadata: SeriesMetadata }) {
  const rows = [
    metadata.native_title && { label: 'Original title', value: metadata.native_title },
    metadata.publisher && { label: 'Magazine', value: metadata.publisher },
    metadata.country && { label: 'Country of origin', value: metadata.country },
    metadata.demographic && { label: 'Demographic', value: metadata.demographic },
    metadata.popularity != null && {
      label: 'On lists',
      value: metadata.popularity.toLocaleString('en-GB'),
    },
  ].filter(Boolean) as { label: string; value: string }[]

  if (!metadata.synopsis && rows.length === 0) return null

  return (
    <Card as="section" elevated className="flex flex-col gap-space-md">
      <h2 className="text-headline-sm text-on-surface">Synopsis</h2>
      {metadata.synopsis ? (
        <div className="flex flex-col gap-space-sm">
          {paragraphs(metadata.synopsis).map((line, index) => (
            <p key={index} className="text-body-md text-on-surface-variant">
              {line}
            </p>
          ))}
        </div>
      ) : (
        <p className="text-body-sm text-outline">No provider returned a synopsis.</p>
      )}
      {rows.length > 0 && (
        <div className="flex flex-col gap-space-xs border-t border-outline-variant pt-space-md">
          {rows.map((row) => (
            <Row key={row.label} label={row.label} value={row.value} />
          ))}
        </div>
      )}
    </Card>
  )
}
```

- [ ] **Step 2: Write the similar works panel**

Create `frontend/src/features/series/SimilarWorks.tsx`:

```tsx
import { Card } from '../../ui'
import type { SimilarWork } from '../../lib/api'

/**
 * AniList's own recommendations for this manga, strongest first. Nothing here
 * is a link: the recommended work is not necessarily on the user's lists, so
 * there is no series of ours to navigate to, and a card that looks clickable
 * and is not is worse than one that does not.
 */
export function SimilarWorks({ items }: { items: SimilarWork[] }) {
  if (items.length === 0) return null

  return (
    <Card as="section" elevated className="flex flex-col gap-space-md">
      <h2 className="text-headline-sm text-on-surface">Similar works</h2>
      <div className="flex flex-col gap-space-sm">
        {items.map((item) => (
          <div key={item.media_id} className="flex items-center gap-space-sm">
            <div className="h-16 w-12 shrink-0 overflow-hidden rounded bg-surface-container-highest">
              {item.cover_url && (
                <img
                  src={item.cover_url}
                  alt=""
                  className="h-full w-full object-cover"
                  loading="lazy"
                />
              )}
            </div>
            <div className="flex min-w-0 flex-col gap-0.5">
              <span className="truncate text-body-md font-semibold text-on-surface">
                {item.title ?? 'Untitled'}
              </span>
              {item.genres.length > 0 && (
                <span className="truncate font-mono text-label-sm text-outline">
                  {item.genres.slice(0, 3).join(' · ')}
                </span>
              )}
              <span className="font-mono text-label-sm text-outline">
                {item.score != null && (
                  <span className="text-tertiary">★ {item.score.toFixed(2)}</span>
                )}
                {item.score != null && item.chapters != null && ' · '}
                {item.chapters != null && `${item.chapters} chapters`}
              </span>
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}
```

- [ ] **Step 3: Write the character grid**

Create `frontend/src/features/series/CharacterGrid.tsx`:

```tsx
import type { SeriesCharacter } from '../../lib/api'

const ROLE_LABEL: Record<string, string> = {
  MAIN: 'Main',
  SUPPORTING: 'Supporting',
  BACKGROUND: 'Background',
}

/**
 * Only AniList serves characters — MyAnimeList has none for manga at all — so
 * a series synced from MyAnimeList alone shows the empty sentence rather than
 * an empty grid that reads as a loading failure.
 */
export function CharacterGrid({ characters }: { characters: SeriesCharacter[] }) {
  if (characters.length === 0) {
    return (
      <p className="text-body-sm text-outline">
        No characters recorded. Only AniList publishes them, and this series is not
        matched to an AniList entry.
      </p>
    )
  }

  return (
    <div className="grid grid-cols-2 gap-space-md sm:grid-cols-3 lg:grid-cols-4">
      {characters.map((character) => (
        <div key={character.name} className="flex flex-col gap-space-xs">
          <div className="aspect-[2/3] overflow-hidden rounded-lg bg-surface-container-highest">
            {character.image_url && (
              <img
                src={character.image_url}
                alt=""
                className="h-full w-full object-cover"
                loading="lazy"
              />
            )}
          </div>
          <span className="truncate text-body-sm font-semibold text-on-surface">
            {character.name}
          </span>
          {character.role && (
            <span className="font-mono text-label-sm text-outline">
              {ROLE_LABEL[character.role] ?? character.role}
            </span>
          )}
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 4: Verify the build and the classes**

```bash
cd frontend
npm run build
grep -r "aspect-\[2/3\]" dist/ | head -1
grep -r "lg:grid-cols-4" dist/ | head -1
```

Expected: build succeeds, both greps match.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/series/SynopsisPanel.tsx \
        frontend/src/features/series/SimilarWorks.tsx \
        frontend/src/features/series/CharacterGrid.tsx
git commit -m "feat(web): render synopsis, similar works and characters

AniList's description carries HTML. It is stripped and rendered as text rather
than injected as markup: trusting a third party's sanitiser with our DOM is an
injection the moment theirs slips."
```

---

## Task 13: The private notes panel

**Files:**
- Create: `frontend/src/features/series/NotesPanel.tsx`
- Modify: `frontend/src/features/series/useSeriesDetail.ts`

**Interfaces:**
- Consumes: `api.saveNotes` from Task 9; `metadata.notes` and `metadata.user_tags` from Task 4.
- Produces: `useSeriesDetail` additionally returns `saveNotes(notes: string, tags: string[]): Promise<void>`; `<NotesPanel metadata={SeriesMetadata} onSave={...} />`. Task 14 composes it.

The note is the provider's own field, not a local one — AniList's `MediaList.notes`, MyAnimeList's `my_list_status.comments`. The write is queued, so the panel says the note was queued rather than claiming it has landed, and the saved value reappears on the next `list_sync`.

- [ ] **Step 1: Extend the hook**

In `frontend/src/features/series/useSeriesDetail.ts`:

```typescript
  // Optimistic like the other two writes, but the note lands on a provider
  // through a job — so what is shown is "queued", and the value the provider
  // actually kept comes back with the next list_sync.
  const saveNotes = useCallback(
    async (notes: string, tags: string[]) => {
      let previous: SeriesDetail | null = null
      setData((current) => {
        previous = current
        return current
          ? { ...current, metadata: { ...current.metadata, notes, user_tags: tags } }
          : current
      })
      try {
        await api.saveNotes(id, notes, tags)
      } catch (failure) {
        if (previous) setData(previous)
        throw failure
      }
    },
    [id, setData],
  )
```

Return it from the hook.

- [ ] **Step 2: Write the panel**

Create `frontend/src/features/series/NotesPanel.tsx`:

```tsx
import { useEffect, useState } from 'react'

import { Button, NoticeBar } from '../../ui'
import type { SeriesMetadata } from '../../lib/api'
import { messageOf } from '../../lib/api'

const MAX_NOTE = 5000

export function NotesPanel({
  metadata,
  onSave,
}: {
  metadata: SeriesMetadata
  onSave: (notes: string, tags: string[]) => Promise<void>
}) {
  const [draft, setDraft] = useState(metadata.notes ?? '')
  const [saving, setSaving] = useState(false)
  const [outcome, setOutcome] = useState<{ text: string; tone: 'info' | 'error' } | null>(null)

  // A note that arrives from a later refresh replaces the draft only when the
  // user has not started editing — otherwise a background reload would delete
  // what they were halfway through typing.
  useEffect(() => {
    setDraft((current) => (current === '' ? metadata.notes ?? '' : current))
  }, [metadata.notes])

  const save = async () => {
    setSaving(true)
    setOutcome(null)
    try {
      await onSave(draft, metadata.user_tags)
      setOutcome({ text: 'Note queued for your reading lists.', tone: 'info' })
    } catch (failure) {
      setOutcome({ text: messageOf(failure), tone: 'error' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-space-md">
      <div className="flex flex-wrap items-center justify-between gap-space-sm">
        <h2 className="text-headline-sm text-on-surface">Your note</h2>
        <span className="font-mono text-label-sm text-outline">
          Visible only to you · {draft.length} / {MAX_NOTE}
        </span>
      </div>

      <textarea
        value={draft}
        maxLength={MAX_NOTE}
        rows={6}
        onChange={(event) => setDraft(event.target.value)}
        aria-label="Your note on this series"
        className="w-full rounded-lg bg-surface-container-lowest p-space-md text-body-md text-on-surface placeholder:text-outline focus:outline-none focus:ring-1 focus:ring-primary"
        placeholder="Kept on your own list entry, not on this server."
      />

      <div className="flex flex-wrap items-center justify-between gap-space-sm">
        {/* Only MyAnimeList has free tags; AniList's customLists are named
            lists, not tags. The row is absent when nothing carries any. */}
        {metadata.user_tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {metadata.user_tags.map((tag) => (
              <span
                key={tag}
                className="rounded bg-surface-container-high px-2 py-0.5 font-mono text-label-sm text-on-surface-variant"
              >
                #{tag}
              </span>
            ))}
          </div>
        )}
        <Button
          variant="primary"
          icon="save"
          disabled={saving || draft === (metadata.notes ?? '')}
          onClick={() => void save()}
        >
          {saving ? 'Saving…' : 'Save note'}
        </Button>
      </div>

      {outcome && <NoticeBar tone={outcome.tone} text={outcome.text} />}
    </div>
  )
}
```

- [ ] **Step 3: Verify the build and the classes**

```bash
cd frontend
npm run build
grep -r "focus:ring-primary" dist/ | head -1
```

Expected: build succeeds, the grep matches. Check `NoticeBar`'s props before building — if `tone` does not accept `'info'`, use the tone it does and adjust the type here rather than adding a tone to `NoticeBar` from this task.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/series/NotesPanel.tsx \
        frontend/src/features/series/useSeriesDetail.ts
git commit -m "feat(web): edit the private note a provider keeps for a series

The write goes through a job, so the panel says the note was queued rather
than claiming it landed, and a background refresh never overwrites a draft
the user is halfway through."
```

---

## Task 14: Compose the screen

**Files:**
- Modify: `backend/app/api/routes_series.py` (`series_detail` serves `reading_minutes_per_chapter`)
- Test: `backend/tests/test_api.py`
- Modify: `frontend/src/lib/api.ts` (`SeriesDetail.reading_minutes_per_chapter`)
- Modify: `frontend/src/features/series/SeriesDetailPage.tsx`

**Interfaces:**
- Consumes: every component from Tasks 10-13.
- Produces: the finished screen. Nothing consumes it.

The remaining-time figure `ProgressManager` renders is derived from `reading_minutes_per_chapter`, which already exists in `app/settings_store.py` with a default of 8. Serving it on the detail payload costs one row read and saves the screen a second request for the whole settings blob.

The layout is the mockup's: a twelve-column hero with the cover on three, then a two-column body — the progress manager and the tabbed panel on the left, the sync targets, download controls, synopsis and similar works on the right.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_api.py`:

```python
async def test_series_detail_carries_the_reading_pace_setting(client):
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta)
                values ('Eleceed', 'eleceed', false, '{}'::jsonb)
                """
            )
        )
        await session.commit()

    body = (await client.get("/api/series/1")).json()
    # The default in settings_store, because nothing has set the key.
    assert body["reading_minutes_per_chapter"] == 8
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest \
  tests/test_api.py -k reading_pace -q
```

Expected: FAIL — `KeyError: 'reading_minutes_per_chapter'`.

- [ ] **Step 3: Serve the setting**

In `backend/app/api/routes_series.py`, add the import:

```python
from app import settings_store
```

and the key to the detail payload's returned dict:

```python
        # The detail screen derives "chapters left, about Nh" from this. Served
        # here rather than fetched from /api/settings, which would cost the
        # screen a second request for the whole settings blob and its provider
        # health with it.
        "reading_minutes_per_chapter": int(
            await settings_store.get(session, settings_store.READING_MINUTES_PER_CHAPTER)
        ),
```

In `frontend/src/lib/api.ts`, add to `SeriesDetail`:

```typescript
  reading_minutes_per_chapter: number
```

- [ ] **Step 4: Rewrite the page**

Replace `frontend/src/features/series/SeriesDetailPage.tsx` with:

```tsx
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { Button, EmptyState, ErrorState, Icon, NoticeBar, Skeleton, Tabs } from '../../ui'
import { ChapterTable } from './ChapterTable'
import { CharacterGrid } from './CharacterGrid'
import { DownloadControls } from './DownloadControls'
import { MappingPanel } from './MappingPanel'
import { NotesPanel } from './NotesPanel'
import { ProgressManager } from './ProgressManager'
import { ScoreStrip } from './ScoreStrip'
import { SeriesHeader } from './SeriesHeader'
import { SimilarWorks } from './SimilarWorks'
import { SynopsisPanel } from './SynopsisPanel'
import { SyncTargets } from './SyncTargets'
import { totalChapters, useSeriesDetail } from './useSeriesDetail'

type Panel = 'chapters' | 'notes' | 'characters'

// The mockup's own geometry: a twelve-column hero with the cover on three,
// then a two-column body. What the mockup shows and this does not is listed in
// docs/superpowers/plans/2026-09-14-series-detail-complete.md — a weekday
// reading chart, a release cadence, per-chapter release dates and page counts,
// and a ComicInfo validation badge. None of them has a source, and an invented
// figure that fills a gap in a mockup is worse than the gap.
export function SeriesDetailPage() {
  const { id } = useParams<{ id: string }>()
  const seriesId = Number(id)
  const {
    detail,
    notFound,
    error,
    reload,
    toggleAutoDownload,
    download,
    research,
    setProgress,
    setListStatus,
    saveNotes,
  } = useSeriesDetail(seriesId)
  const [panel, setPanel] = useState<Panel>('chapters')

  if (notFound) {
    return (
      <EmptyState
        icon="warning"
        title="Series not found"
        detail="It may have been removed. Head back to the library and pick another one."
        action={
          <Link to="/library">
            <Button variant="surface" icon="book">
              Back to library
            </Button>
          </Link>
        }
      />
    )
  }

  if (!detail && error) {
    return <ErrorState title="Couldn't load this series" detail={error} onRetry={reload} />
  }

  if (!detail) {
    return (
      <div className="flex flex-col gap-space-lg">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    )
  }

  const { series, metadata, mapping, chapters, entries } = detail
  const total = totalChapters(detail)

  return (
    <div className="flex flex-col gap-space-xl">
      <Link
        to="/library"
        className="flex w-fit items-center gap-space-xs text-body-sm text-on-surface-variant hover:text-on-surface"
      >
        <Icon name="chevron" className="h-4 w-4 rotate-90" />
        Back to library
      </Link>

      {/* A page already showing real data stays showing it — a failed
          background refresh says so here instead of collapsing to the
          not-found or first-load error screens above. */}
      {error && (
        <NoticeBar tone="error" text={`Couldn't refresh this series: ${error}`} onRetry={reload} />
      )}

      <section className="grid grid-cols-1 items-start gap-space-xl lg:grid-cols-12">
        <div className="aspect-[2/3] w-56 shrink-0 overflow-hidden rounded-xl bg-surface-container-highest shadow-card sm:w-64 lg:col-span-3 lg:w-full">
          {series.cover_url && (
            <img
              src={series.cover_url}
              alt={`Cover of ${series.title}`}
              className="h-full w-full object-cover"
            />
          )}
        </div>
        <SeriesHeader series={series} metadata={metadata} />
      </section>

      <ScoreStrip metadata={metadata} />

      <div className="grid grid-cols-1 gap-space-lg lg:grid-cols-[1fr_360px]">
        <div className="flex min-w-0 flex-col gap-space-lg">
          <ProgressManager
            detail={detail}
            total={total}
            minutesPerChapter={detail.reading_minutes_per_chapter}
            onProgress={setProgress}
            onStatus={setListStatus}
          />

          <section className="flex flex-col gap-space-md">
            <Tabs
              options={[
                { value: 'chapters', label: 'Chapters', count: chapters.length },
                { value: 'notes', label: 'Your note' },
                // A count only when the enrichment has landed; "(0)" while it
                // is still queued would read as "this manga has no characters".
                {
                  value: 'characters',
                  label: 'Characters',
                  count: metadata.characters.length || null,
                },
              ]}
              value={panel}
              onChange={setPanel}
            />
            {panel === 'chapters' && <ChapterTable chapters={chapters} />}
            {panel === 'notes' && <NotesPanel metadata={metadata} onSave={saveNotes} />}
            {panel === 'characters' && <CharacterGrid characters={metadata.characters} />}
          </section>
        </div>

        <aside className="flex flex-col gap-space-md">
          <MappingPanel mapping={mapping} onResearch={research} />
          <SyncTargets entries={entries} />
          <DownloadControls
            autoDownload={series.auto_download}
            onToggleAutoDownload={toggleAutoDownload}
            onDownload={download}
            onQueued={reload}
          />
          <SynopsisPanel metadata={metadata} />
          <SimilarWorks items={metadata.similar} />
        </aside>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Verify the whole thing**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests -q
.venv/bin/python -m ruff check app/ tests/

cd ../frontend
npm run build
grep -r "lg:grid-cols-\[1fr_360px\]" dist/ | head -1
grep -r "lg:col-span-3" dist/ | head -1
```

Then exercise it in the running stack. The build must include the worker, or the three new job types fail with `no handler registered`:

```bash
cd ..
docker compose build api && docker compose up -d --force-recreate api worker
```

Open `http://localhost:8080/series/<id>` for a series synced from AniList and confirm, by eye: the publisher or country pill row, the native title beside the English one, the author credit, the score strip, the progress stepper and status control, the three tabs, the synopsis and its metadata rows. Then check the enrichment landed:

```bash
docker compose exec -T db psql -U manga -d manga \
  -c "select id, meta->'enrichment'->>'rank', jsonb_array_length(meta->'enrichment'->'characters') from series where id = <id>;"
```

Expected: a rank and a character count, written by the `media_enrich` job the first page load queued.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes_series.py backend/tests/test_api.py \
        frontend/src/lib/api.ts frontend/src/features/series/SeriesDetailPage.tsx
git commit -m "feat(web): compose the series detail screen

The reading pace setting is served on the detail payload rather than fetched
from /api/settings, which would cost the screen a second request for the whole
settings blob and provider health with it."
```

---

## Self-review

**Spec coverage.** Every panel in the mockup is either implemented by a task above or listed in "What the mockup asks for that nothing can serve" with the reason. The redesign spec's own § Series detail requirements — cover and metadata, the mapping and its source, the chapter table with local file state, the sync targets and their last write, auto-download, download a range, re-run the search — were already built and are preserved by Task 14's composition rather than rewritten.

**Placeholders.** None. Every step carries the code it asks for, and every test carries its assertions.

**Type consistency.** `metadata_of(raws, enrichment)` (Task 3) is called with exactly that signature in Task 4 and Task 6. `parse_media_detail` (Task 5) returns `{rank, vote_count, characters, similar}`, which is what `metadata_of` reads out of `enrichment` and what `SeriesMetadata` (Task 9) types. `is_stale(enrichment, now)` (Task 6) is imported by the route in the same task. `Source.set_notes(access_token, media_id, notes, tags)` (Task 8) has one signature across base, both providers and the handler. `useIncrementFlash` moves once, in Task 11, and Task 11 updates both existing importers.

**One gap worth naming.** `metadata.list_updated_at` is null for an AniList-only series: AniList's `MediaList.updatedAt` is a Unix integer, not an ISO string, and Task 3 returns null rather than guessing at a timezone. `ProgressManager` therefore omits the "Last updated" row for those series. Converting it is a one-line follow-up and is deliberately not folded in here.
