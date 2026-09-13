# Anime-to-Manga Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Status: complete

All thirteen tasks were implemented on branch `feat/anime-manga-discovery` and shipped as
PR #19. Backend suite 216 passing, `ruff` clean. What the branch actually looks like, and
why it differs from the spec, is recorded in the "Como ficou" section of the design doc.

The useful part for the next plan is what two whole-branch reviews caught that this plan
itself caused. Each of these was a correct implementation of what is written above:

- **Reusing a shared helper without reading its conflict branch.** The plan told approval
  to create `series` and `list_entry` with `list_sync`'s helpers. `upsert_entry` copies
  every column on conflict, so approving a manga `list_sync` already knew zeroed
  `user_progress_chapter` — the only forward-only guard in the system — and blanked its
  metadata. Needed a separate `upsert_entry_status`. When a plan says "reuse X", it has to
  say which parts of X's behaviour are wanted.
- **"Create the series" with no resolve step.** A suggestion can sit unapproved while
  `list_sync` creates that same manga under another spelling; the plan never said to look
  first, so approval duplicated it. It also never said what to do when the resolved series
  already carries a confirmed source mapping.
- **A confidence threshold expressed as one number.** `score >= 0.80` against a single
  title puts near-misses over the line ("Dragon Ball" vs "Dragon Ball Super" = 0.786). The
  rule had to become score *and* exact normalised title, which meant storing the candidate
  title in `meta.best` — a field the plan never listed.
- **A boolean assigned instead of merged.** The plan's approval step set `auto_download`
  from the request body, so approving an already-followed series with the box unticked
  stopped following it. It is an additive action, `auto_download or :enabled`.
- **A branch left undescribed.** The plan enqueued `CHAPTER_DISCOVER` when
  `download: true`, and said nothing about `download: true` *plus* an unconfident mapping.
  That combination silently dropped the download the user asked for.
- **"Raise `PermanentError` when a target has no account."** Applied literally, one
  disconnected provider retired the job before the other two targets were written. Failure
  policy has to be stated per target and then per job. The same sentence also had no room
  for a target that was never configured at all: MangaDex's credentials are optional, so
  an empty set is the default deployment, and it is an absence, not a failure.
- **Long loops with one commit at the end.** `SUGGEST_BUILD` (a search per source per
  seed) and `ANIME_LIST_SYNC` (a request per MAL anime) both outrun the 900-second lease
  on a real list, and an expired lease is re-leased, so the job runs beside itself. A plan
  that adds a loop over network calls has to say where it commits and renews.
- **A shallow `meta` merge with unconditional keys.** The plan had `source_summary` write
  every key it computed, so one cycle with MangaDex rate-limited erased the stored
  `mangadex_uuid` that `LIST_WRITE` depends on.
- **Exclusion described for correctness, not for cost.** `SUGGEST_BUILD` was told the
  upsert preserves `state`, which is true, so dismissed seeds were still searched — every
  dismissal adding a search per source to every future run, for ever.
- **A third-party build context with no ref.** The plan's compose service built from the
  comick repository's default branch, meaning each build ran whatever that project had
  just pushed, as a service on this host. Pin it.
- **Reused UI shapes carry their own copy.** The Settings provider row rendered comick,
  which has no accounts, as "signed in".
- **A name in the file table that was never built.** `sources/mangadex.py` was to gain
  `search_id`; what it needed was `manga_id_from_candidate`, reading the uuid off a
  candidate the search already returned.
- **A fallback specified from documentation, never checked against the API.** The plan had
  `ANIME_LIST_SYNC` call `/v2/anime/{id}?fields=related_manga` for whatever AniList did not
  resolve. Nobody had called that endpoint with a real token first: it returns an empty
  `related_manga` for every anime, including titles with an unmistakable source manga, because
  MyAnimeList's v2 API never populates that field on the anime endpoint — it links manga to
  manga, not anime to manga. Verified directly against the live API and against 970 MyAnimeList
  anime rows synced with 0 relations among them, then removed; see the design doc's "As built"
  section. A plan that adds a fallback for a documented-but-unverified field has to say it was
  checked against the live service, not just the docs.

Follow-ups deliberately left for a second pass are in issue #21.

**Goal:** Read the user's anime lists, suggest the manga those anime adapt, and make approving a suggestion write the chosen status to MyAnimeList, AniList and MangaDex while the existing pipeline downloads it into Komga.

**Architecture:** Two new tables (`anime_entry`, `suggestion`) hold the discovery state; three new jobs (`ANIME_LIST_SYNC`, `SUGGEST_BUILD`, `LIST_WRITE`) fill them and write status outward; a `comick-source-api` container supplies search and chapter listing for non-MangaDex sites whose downloads the existing `manga-downloader` binary already handles. Nothing in the current download path changes.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 (Core `text()` queries in handlers), asyncpg, Alembic, httpx, pytest + pytest-asyncio, React 18 + TypeScript + Vite, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-13-anime-manga-discovery-design.md`

## Global Constraints

- Handlers are the only layer that writes to the database. Providers, sources and clients return DTOs and stay pure at the edges (`backend/app/handlers/base.py:1-8`).
- Every network response parser is a module-level pure function tested from a JSON fixture in `backend/tests/fixtures/`. No network in tests.
- Database access in handlers and routes uses `session.execute(text(...), params)`, not the ORM. `backend/app/models.py` exists to document the schema and to back Alembic; it is not used for queries.
- Migrations are hand-written SQL via `op.execute`, idempotent (`if not exists`), with a working `downgrade()`. Revision ids follow `000N_<slug>`.
- Comments explain *why*, never *what*. Match the density of the surrounding modules.
- Commits: English, imperative, conventional-commit prefix (`feat:`, `fix:`, `test:`, `docs:`, `chore:`). One focused change per commit. No assistant attribution of any kind.
- Enum values that reach the database are lowercase `StrEnum` members (`backend/app/enums.py`).
- `ListStatus` is shared by anime and manga: `READING` means "watching" on the anime side. Do not add a second enum.
- `LIST_WRITE` writes status only. Reading progress stays owned by `progress_push`, which only moves forward.
- Tests requiring Postgres assume the database from `docker-compose.yml` on `localhost:5433` (`backend/tests/conftest.py:8-9`), schema applied by `alembic upgrade head`.
- Run tests from `backend/`: `.venv/bin/python -m pytest`. Run lint with `.venv/bin/python -m ruff check app tests`.

---

## File Structure

**Created**

| File | Responsibility |
|---|---|
| `backend/alembic/versions/0003_discovery.py` | `anime_entry` and `suggestion` tables |
| `backend/app/discovery/__init__.py` | package marker |
| `backend/app/discovery/seeds.py` | pure: relation graph → deduplicated suggestion seeds, ranking |
| `backend/app/discovery/status_sync.py` | pure: internal status → the four dialects |
| `backend/app/handlers/anime_list_sync.py` | `ANIME_LIST_SYNC` job |
| `backend/app/handlers/suggest_build.py` | `SUGGEST_BUILD` job |
| `backend/app/handlers/list_write.py` | `LIST_WRITE` job |
| `backend/app/sources/comick_client.py` | HTTP client + pure parsers for comick-source-api |
| `backend/app/sources/comick.py` | `ComickSource` subclasses registered as sources |
| `backend/app/api/routes_discovery.py` | suggestion list, add, dismiss, refresh |
| `frontend/src/pages/Discovery.tsx` | Discovery screen |

**Modified**

| File | Change |
|---|---|
| `backend/app/enums.py` | `SuggestionState`; three `JobType` members |
| `backend/app/models.py` | `AnimeEntry`, `Suggestion` |
| `backend/app/providers/base.py` | `RelatedManga`, `AnimeEntryDTO`, `fetch_anime_list`, `set_status` |
| `backend/app/providers/anilist.py` | anime list query, relations parser, status mutation, manga metadata batch |
| `backend/app/providers/mal.py` | anime list, `related_manga` detail, status write |
| `backend/app/sources/mangadex.py` | `set_reading_status`, `search_id` |
| `backend/app/settings_store.py` | `CRON_ANIME_LIST_SYNC` |
| `backend/app/config.py` | `comick_api_url` |
| `backend/app/worker/main.py` | register new handlers and the anime cron |
| `backend/app/api/main.py` | include `routes_discovery` |
| `backend/app/api/routes_settings.py` | new cron editable, comick health |
| `backend/app/handlers/komga_scan.py` | mark books read when the chosen status is completed |
| `docker-compose.yml` | `comick` service |
| `frontend/src/api.ts`, `App.tsx`, `pages/Settings.tsx` | Discovery wiring |

---

### Task 1: Schema for anime entries and suggestions

**Files:**
- Create: `backend/alembic/versions/0003_discovery.py`
- Modify: `backend/app/enums.py`
- Modify: `backend/app/models.py`
- Test: `backend/tests/test_discovery_schema.py`

**Interfaces:**
- Consumes: nothing.
- Produces: tables `anime_entry` and `suggestion` as specified; `SuggestionState.NEW|DISMISSED|ADDED`; `JobType.ANIME_LIST_SYNC|SUGGEST_BUILD|LIST_WRITE`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_discovery_schema.py
"""The discovery tables, asserted against a real database.

A unique constraint that does not exist only fails when two rows collide in
production, so the constraint is the test.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import get_sessionmaker
from app.enums import JobType, SuggestionState

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate anime_entry, suggestion restart identity cascade"))
        await session.commit()
    yield


async def test_an_anime_entry_is_unique_per_provider_and_media_id():
    async with get_sessionmaker()() as session:
        insert = text(
            """
            insert into anime_entry (provider, provider_media_id, status, progress_episode,
                                     synonyms, related_manga, raw, updated_at)
            values ('anilist', '101', 'reading', 3, '[]'::jsonb, '[]'::jsonb, '{}'::jsonb, now())
            """
        )
        await session.execute(insert)
        await session.commit()
        with pytest.raises(IntegrityError):
            await session.execute(insert)
            await session.commit()


async def test_a_suggestion_defaults_to_the_new_state():
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into suggestion (provider, provider_media_id, title, alt_ids, meta)
                values ('anilist', '55', 'Vinland Saga', '{}'::jsonb, '{}'::jsonb)
                """
            )
        )
        await session.commit()
        state = (await session.execute(text("select state from suggestion"))).scalar_one()
    assert state == SuggestionState.NEW


async def test_dropping_a_series_leaves_the_suggestion_behind():
    """Dismissal history outlives the library: it is what stops a resurrection."""
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    """
                    insert into series (canonical_title, slug, needs_review, meta, created_at)
                    values ('X', 'x-discovery', false, '{}'::jsonb, now()) returning id
                    """
                )
            )
        ).scalar_one()
        await session.execute(
            text(
                """
                insert into suggestion (provider, provider_media_id, title, series_id,
                                        alt_ids, meta)
                values ('anilist', '77', 'X', :sid, '{}'::jsonb, '{}'::jsonb)
                """
            ),
            {"sid": series_id},
        )
        await session.commit()
        await session.execute(text("delete from series where id = :sid"), {"sid": series_id})
        await session.commit()
        row = (await session.execute(text("select series_id from suggestion"))).scalar_one()
    assert row is None


def test_the_new_job_types_exist():
    assert JobType.ANIME_LIST_SYNC == "anime_list_sync"
    assert JobType.SUGGEST_BUILD == "suggest_build"
    assert JobType.LIST_WRITE == "list_write"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_discovery_schema.py -v`
Expected: FAIL — `ImportError: cannot import name 'SuggestionState'`.

- [ ] **Step 3: Add the enum members**

```python
# backend/app/enums.py — add
class SuggestionState(StrEnum):
    NEW = "new"
    DISMISSED = "dismissed"
    ADDED = "added"
```

In `JobType`, add:

```python
    ANIME_LIST_SYNC = "anime_list_sync"
    SUGGEST_BUILD = "suggest_build"
    LIST_WRITE = "list_write"
```

- [ ] **Step 4: Write the migration**

```python
# backend/alembic/versions/0003_discovery.py
"""anime entries and manga suggestions

Revision ID: 0003_discovery
Revises: 0002_auto_download
Create Date: 2026-09-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_discovery"
down_revision: str | None = "0002_auto_download"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        create table if not exists anime_entry (
            id bigserial primary key,
            provider varchar(20) not null,
            provider_media_id varchar(50) not null,
            title_romaji varchar(500),
            title_english varchar(500),
            synonyms jsonb not null default '[]'::jsonb,
            status varchar(20) not null,
            progress_episode integer not null default 0,
            total_episodes integer,
            cover_url text,
            related_manga jsonb not null default '[]'::jsonb,
            raw jsonb not null default '{}'::jsonb,
            updated_at timestamptz not null default now(),
            constraint uq_anime_entry_provider_media unique (provider, provider_media_id)
        )
        """
    )
    op.execute(
        """
        create table if not exists suggestion (
            id bigserial primary key,
            provider varchar(20) not null,
            provider_media_id varchar(50) not null,
            alt_ids jsonb not null default '{}'::jsonb,
            title varchar(500) not null,
            cover_url text,
            total_chapters integer,
            year integer,
            publishing_status varchar(20),
            state varchar(20) not null default 'new',
            rank_score numeric(5, 4) not null default 0,
            series_id bigint references series(id) on delete set null,
            meta jsonb not null default '{}'::jsonb,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now(),
            constraint uq_suggestion_provider_media unique (provider, provider_media_id)
        )
        """
    )
    # The Discovery screen reads one slice, ordered: new suggestions, best first.
    op.execute(
        "create index if not exists ix_suggestion_state_rank on suggestion (state, rank_score desc)"
    )


def downgrade() -> None:
    op.execute("drop index if exists ix_suggestion_state_rank")
    op.execute("drop table if exists suggestion")
    op.execute("drop table if exists anime_entry")
```

- [ ] **Step 5: Mirror the tables in `models.py`**

Append to `backend/app/models.py`, and extend its `from app.enums import ...` line with `SuggestionState`:

```python
class AnimeEntry(Base):
    """One anime as it exists on a remote list provider, relations included."""

    __tablename__ = "anime_entry"
    __table_args__ = (
        UniqueConstraint("provider", "provider_media_id", name="uq_anime_entry_provider_media"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider: Mapped[Provider] = mapped_column(String(20), nullable=False)
    provider_media_id: Mapped[str] = mapped_column(String(50), nullable=False)
    title_romaji: Mapped[str | None] = mapped_column(String(500))
    title_english: Mapped[str | None] = mapped_column(String(500))
    synonyms: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[ListStatus] = mapped_column(String(20), nullable=False)
    progress_episode: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_episodes: Mapped[int | None] = mapped_column(Integer)
    cover_url: Mapped[str | None] = mapped_column(Text)
    related_manga: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Suggestion(Base):
    """A manga worth reading because an anime on the list adapts it."""

    __tablename__ = "suggestion"
    __table_args__ = (
        UniqueConstraint("provider", "provider_media_id", name="uq_suggestion_provider_media"),
        Index("ix_suggestion_state_rank", "state", "rank_score"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider: Mapped[Provider] = mapped_column(String(20), nullable=False)
    provider_media_id: Mapped[str] = mapped_column(String(50), nullable=False)
    alt_ids: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    cover_url: Mapped[str | None] = mapped_column(Text)
    total_chapters: Mapped[int | None] = mapped_column(Integer)
    year: Mapped[int | None] = mapped_column(Integer)
    publishing_status: Mapped[str | None] = mapped_column(String(20))
    state: Mapped[SuggestionState] = mapped_column(
        String(20), nullable=False, default=SuggestionState.NEW
    )
    rank_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0)
    series_id: Mapped[int | None] = mapped_column(ForeignKey("series.id", ondelete="SET NULL"))
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

- [ ] **Step 6: Apply the migration and run the tests**

Run: `cd backend && .venv/bin/python -m alembic upgrade head && .venv/bin/python -m pytest tests/test_discovery_schema.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 7: Commit**

```bash
git add backend/alembic/versions/0003_discovery.py backend/app/enums.py backend/app/models.py backend/tests/test_discovery_schema.py
git commit -m "feat(discovery): add the anime entry and suggestion tables"
```

---

### Task 2: Read the AniList anime list with its relation graph

**Files:**
- Modify: `backend/app/providers/base.py`
- Modify: `backend/app/providers/anilist.py`
- Create: `backend/tests/fixtures/anilist_anime_list.json`
- Test: `backend/tests/test_anime_parse.py`

**Interfaces:**
- Consumes: `ListStatus`, `Provider` from Task 1's unchanged enums.
- Produces:
  - `RelatedManga(provider: Provider, media_id: str, relation: str, format: str | None, title: str)`
  - `AnimeEntryDTO(provider, media_id, status, title_romaji, title_english, synonyms, progress_episode, total_episodes, cover_url, related_manga: list[RelatedManga], raw)` with a `titles` property, same shape as `ListEntryDTO.titles`
  - `ListSource.fetch_anime_list(access_token) -> list[AnimeEntryDTO]`
  - `app.providers.anilist.parse_anime_list(data: dict) -> list[AnimeEntryDTO]`

- [ ] **Step 1: Write the fixture**

```json
{
  "MediaListCollection": {
    "lists": [
      {
        "entries": [
          {
            "status": "COMPLETED",
            "progress": 24,
            "media": {
              "id": 21,
              "episodes": 24,
              "synonyms": ["VS"],
              "title": {"romaji": "Vinland Saga", "english": "Vinland Saga", "native": "ヴィンランド・サガ"},
              "coverImage": {"large": "https://img/vs.jpg"},
              "relations": {
                "edges": [
                  {
                    "relationType": "SOURCE",
                    "node": {"id": 3000, "type": "MANGA", "format": "MANGA",
                             "title": {"romaji": "Vinland Saga", "english": "Vinland Saga"}}
                  },
                  {
                    "relationType": "SEQUEL",
                    "node": {"id": 22, "type": "ANIME", "format": "TV",
                             "title": {"romaji": "Vinland Saga Season 2", "english": null}}
                  }
                ]
              }
            }
          },
          {
            "status": "CURRENT",
            "progress": 5,
            "media": {
              "id": 40,
              "episodes": null,
              "synonyms": [],
              "title": {"romaji": "Mushoku Tensei", "english": null, "native": "無職転生"},
              "coverImage": {"large": "https://img/mt.jpg"},
              "relations": {
                "edges": [
                  {
                    "relationType": "SOURCE",
                    "node": {"id": 4000, "type": "MANGA", "format": "NOVEL",
                             "title": {"romaji": "Mushoku Tensei (LN)", "english": null}}
                  },
                  {
                    "relationType": "ADAPTATION",
                    "node": {"id": 4001, "type": "MANGA", "format": "MANGA",
                             "title": {"romaji": "Mushoku Tensei", "english": "Jobless Reincarnation"}}
                  }
                ]
              }
            }
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_anime_parse.py
from app.enums import ListStatus, Provider
from app.providers.anilist import parse_anime_list


def test_anilist_reads_episode_progress_not_chapter_progress(fixture):
    entries = parse_anime_list(fixture("anilist_anime_list.json"))
    assert entries[0].progress_episode == 24
    assert entries[0].total_episodes == 24
    assert entries[1].total_episodes is None


def test_watching_maps_onto_the_shared_reading_status(fixture):
    entries = parse_anime_list(fixture("anilist_anime_list.json"))
    assert entries[0].status is ListStatus.COMPLETED
    assert entries[1].status is ListStatus.READING


def test_only_manga_relations_survive(fixture):
    """A sequel anime and a light novel are both relations, and neither is readable here."""
    first, second = parse_anime_list(fixture("anilist_anime_list.json"))
    assert [r.media_id for r in first.related_manga] == ["3000"]
    assert [r.media_id for r in second.related_manga] == ["4001"]
    assert second.related_manga[0].relation == "ADAPTATION"
    assert second.related_manga[0].provider is Provider.ANILIST


def test_the_relation_keeps_the_title_it_will_be_deduplicated_by(fixture):
    first = parse_anime_list(fixture("anilist_anime_list.json"))[0]
    assert first.related_manga[0].title == "Vinland Saga"


def test_the_native_title_is_kept_as_a_synonym(fixture):
    first = parse_anime_list(fixture("anilist_anime_list.json"))[0]
    assert "ヴィンランド・サガ" in first.synonyms
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_anime_parse.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_anime_list'`.

- [ ] **Step 4: Add the DTOs to the provider contract**

In `backend/app/providers/base.py`, after `ListEntryDTO`:

```python
@dataclass(frozen=True)
class RelatedManga:
    """A manga a provider says an anime adapts, or is adapted from."""

    provider: Provider
    media_id: str
    relation: str
    title: str
    format: str | None = None


@dataclass(frozen=True)
class AnimeEntryDTO:
    provider: Provider
    media_id: str
    status: ListStatus
    title_romaji: str | None = None
    title_english: str | None = None
    synonyms: list[str] = field(default_factory=list)
    progress_episode: int = 0
    total_episodes: int | None = None
    cover_url: str | None = None
    related_manga: list[RelatedManga] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def display_title(self) -> str:
        return self.title_english or self.title_romaji or f"{self.provider}:{self.media_id}"
```

Add to the `ListSource` class a non-abstract default, so a provider without anime support stays valid:

```python
    async def fetch_anime_list(self, access_token: str) -> list["AnimeEntryDTO"]:
        """Every anime entry on the authenticated user's list, relations included."""
        return []

    async def set_status(self, access_token: str, media_id: str, status: ListStatus) -> None:
        """Write the manga's list status, creating the entry when it is absent."""
        raise NotImplementedError
```

Export both DTOs from `backend/app/providers/__init__.py` alongside `ListEntryDTO`.

- [ ] **Step 5: Add the query and the parser to `anilist.py`**

```python
ANIME_STATUS_MAP = {
    "CURRENT": ListStatus.READING,
    "REPEATING": ListStatus.READING,
    "PLANNING": ListStatus.PLAN_TO_READ,
    "COMPLETED": ListStatus.COMPLETED,
    "PAUSED": ListStatus.ON_HOLD,
    "DROPPED": ListStatus.DROPPED,
}

# Formats that can actually be read as a manga. NOVEL and ONE_SHOT are relations
# too, and suggesting either would be suggesting something that does not exist.
MANGA_FORMATS = {"MANGA", "MANHWA", "MANHUA", "OEL"}
WANTED_RELATIONS = {"SOURCE", "ADAPTATION"}

ANIME_LIST_QUERY = """
query ($userId: Int) {
  MediaListCollection(userId: $userId, type: ANIME) {
    lists {
      entries {
        status
        progress
        media {
          id
          episodes
          synonyms
          title { romaji english native }
          coverImage { large }
          relations {
            edges {
              relationType
              node { id type format title { romaji english } }
            }
          }
        }
      }
    }
  }
}
"""
```

```python
def parse_relations(media: dict[str, Any]) -> list[RelatedManga]:
    related: list[RelatedManga] = []
    for edge in ((media.get("relations") or {}).get("edges") or []):
        node = edge.get("node") or {}
        if edge.get("relationType") not in WANTED_RELATIONS:
            continue
        if node.get("type") != "MANGA" or node.get("format") not in MANGA_FORMATS:
            continue
        title = node.get("title") or {}
        related.append(
            RelatedManga(
                provider=Provider.ANILIST,
                media_id=str(node.get("id")),
                relation=edge["relationType"],
                title=title.get("romaji") or title.get("english") or "",
                format=node.get("format"),
            )
        )
    return related


def parse_anime_list(data: dict[str, Any]) -> list[AnimeEntryDTO]:
    """Pure parser, so the shape of an AniList anime response is testable from a fixture."""
    entries: list[AnimeEntryDTO] = []
    for group in data.get("MediaListCollection", {}).get("lists", []) or []:
        for entry in group.get("entries", []) or []:
            media = entry.get("media") or {}
            title = media.get("title") or {}
            synonyms = [s for s in (media.get("synonyms") or []) if s]
            native = title.get("native")
            if native:
                synonyms.append(native)
            entries.append(
                AnimeEntryDTO(
                    provider=Provider.ANILIST,
                    media_id=str(media.get("id")),
                    status=ANIME_STATUS_MAP.get(entry.get("status", ""), ListStatus.PLAN_TO_READ),
                    title_romaji=title.get("romaji"),
                    title_english=title.get("english"),
                    synonyms=synonyms,
                    progress_episode=int(entry.get("progress") or 0),
                    total_episodes=media.get("episodes"),
                    cover_url=(media.get("coverImage") or {}).get("large"),
                    related_manga=parse_relations(media),
                    raw=entry,
                )
            )
    return entries
```

Add the fetch method to `AniListSource`:

```python
    async def fetch_anime_list(self, access_token: str) -> list[AnimeEntryDTO]:
        user_id, _ = await self.viewer(access_token)
        data = await self._post(access_token, ANIME_LIST_QUERY, {"userId": user_id})
        return parse_anime_list(data)
```

Extend the import from `app.providers.base` with `AnimeEntryDTO` and `RelatedManga`.

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_anime_parse.py -v`
Expected: PASS, 5 tests.

- [ ] **Step 7: Commit**

```bash
git add backend/app/providers/base.py backend/app/providers/__init__.py backend/app/providers/anilist.py backend/tests/fixtures/anilist_anime_list.json backend/tests/test_anime_parse.py
git commit -m "feat(anilist): read the anime list with its manga relations"
```

---

### Task 3: Read the MyAnimeList anime list and its related manga

**Files:**
- Modify: `backend/app/providers/mal.py`
- Create: `backend/tests/fixtures/mal_anime_page.json`, `backend/tests/fixtures/mal_anime_detail.json`
- Test: `backend/tests/test_anime_parse.py` (append)

**Interfaces:**
- Consumes: `AnimeEntryDTO`, `RelatedManga` from Task 2.
- Produces:
  - `app.providers.mal.parse_anime_page(page: dict) -> list[AnimeEntryDTO]`
  - `app.providers.mal.parse_related_manga(detail: dict) -> list[RelatedManga]`
  - `MyAnimeListSource.fetch_anime_list`, `MyAnimeListSource.fetch_related_manga(access_token, media_id) -> list[RelatedManga]`

- [ ] **Step 1: Write the fixtures**

```json
// backend/tests/fixtures/mal_anime_page.json
{
  "data": [
    {
      "node": {
        "id": 21,
        "title": "Vinland Saga",
        "main_picture": {"large": "https://img/vs-mal.jpg"},
        "alternative_titles": {"en": "Vinland Saga", "ja": "ヴィンランド・サガ", "synonyms": ["VS"]},
        "num_episodes": 24
      },
      "list_status": {"status": "completed", "num_episodes_watched": 24}
    },
    {
      "node": {
        "id": 99,
        "title": "Kaijuu 8-gou",
        "main_picture": {"large": "https://img/k8.jpg"},
        "alternative_titles": {"en": "Kaiju No. 8", "ja": "怪獣8号", "synonyms": []},
        "num_episodes": 12
      },
      "list_status": {"status": "watching", "num_episodes_watched": 7}
    }
  ],
  "paging": {}
}
```

```json
// backend/tests/fixtures/mal_anime_detail.json
{
  "id": 99,
  "title": "Kaijuu 8-gou",
  "related_manga": [
    {"node": {"id": 122763, "title": "Kaijuu 8-gou"}, "relation_type": "source",
     "relation_type_formatted": "Original Source"},
    {"node": {"id": 140000, "title": "Kaijuu 8-gou: B-side"}, "relation_type": "side_story",
     "relation_type_formatted": "Side Story"}
  ]
}
```

- [ ] **Step 2: Write the failing test (append to `tests/test_anime_parse.py`)**

```python
from app.providers.mal import parse_anime_page, parse_related_manga


def test_mal_reads_watched_episodes_from_list_status(fixture):
    entries = parse_anime_page(fixture("mal_anime_page.json"))
    assert entries[0].progress_episode == 24
    assert entries[1].progress_episode == 7
    assert entries[1].total_episodes == 12


def test_mal_watching_maps_onto_the_shared_reading_status(fixture):
    entries = parse_anime_page(fixture("mal_anime_page.json"))
    assert entries[0].status is ListStatus.COMPLETED
    assert entries[1].status is ListStatus.READING


def test_mal_keeps_english_and_synonym_spellings(fixture):
    entry = parse_anime_page(fixture("mal_anime_page.json"))[0]
    assert entry.title_english == "Vinland Saga"
    assert "VS" in entry.synonyms
    assert "ヴィンランド・サガ" in entry.synonyms


def test_only_the_source_relation_becomes_a_manga_candidate(fixture):
    """A side story is a different book, and suggesting it is suggesting the wrong one."""
    related = parse_related_manga(fixture("mal_anime_detail.json"))
    assert [r.media_id for r in related] == ["122763"]
    assert related[0].provider is Provider.MAL
    assert related[0].title == "Kaijuu 8-gou"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_anime_parse.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_anime_page'`.

- [ ] **Step 4: Implement in `mal.py`**

```python
ANIME_LIST_FIELDS = "list_status,alternative_titles,num_episodes,main_picture,title"
ANIME_DETAIL_FIELDS = "related_manga"

ANIME_STATUS_MAP = {
    "watching": ListStatus.READING,
    "plan_to_watch": ListStatus.PLAN_TO_READ,
    "completed": ListStatus.COMPLETED,
    "on_hold": ListStatus.ON_HOLD,
    "dropped": ListStatus.DROPPED,
}

# MyAnimeList names many relations; only the original work is the same story.
WANTED_RELATIONS = {"source", "adaptation"}


def parse_anime_page(page: dict[str, Any]) -> list[AnimeEntryDTO]:
    entries: list[AnimeEntryDTO] = []
    for item in page.get("data", []) or []:
        node = item.get("node") or {}
        status = item.get("list_status") or {}
        alt = node.get("alternative_titles") or {}
        synonyms = [s for s in (alt.get("synonyms") or []) if s]
        if alt.get("ja"):
            synonyms.append(alt["ja"])
        entries.append(
            AnimeEntryDTO(
                provider=Provider.MAL,
                media_id=str(node.get("id")),
                status=ANIME_STATUS_MAP.get(status.get("status", ""), ListStatus.PLAN_TO_READ),
                title_romaji=node.get("title"),
                title_english=alt.get("en") or None,
                synonyms=synonyms,
                progress_episode=int(status.get("num_episodes_watched") or 0),
                total_episodes=node.get("num_episodes") or None,
                cover_url=(node.get("main_picture") or {}).get("large"),
                related_manga=[],
                raw=item,
            )
        )
    return entries


def parse_related_manga(detail: dict[str, Any]) -> list[RelatedManga]:
    related: list[RelatedManga] = []
    for item in detail.get("related_manga", []) or []:
        if item.get("relation_type") not in WANTED_RELATIONS:
            continue
        node = item.get("node") or {}
        related.append(
            RelatedManga(
                provider=Provider.MAL,
                media_id=str(node.get("id")),
                relation=str(item.get("relation_type", "")).upper(),
                title=node.get("title") or "",
            )
        )
    return related
```

```python
    async def fetch_anime_list(self, access_token: str) -> list[AnimeEntryDTO]:
        entries: list[AnimeEntryDTO] = []
        url: str | None = f"{API_BASE}/users/@me/animelist"
        params: dict[str, Any] | None = {
            "fields": ANIME_LIST_FIELDS,
            "limit": PAGE_LIMIT,
            "nsfw": "true",
        }
        while url:
            page = await self._get(access_token, url, params)
            entries.extend(parse_anime_page(page))
            url = (page.get("paging") or {}).get("next")
            params = None
        return entries

    async def fetch_related_manga(self, access_token: str, media_id: str) -> list[RelatedManga]:
        """One request per anime, so this is only worth calling when AniList came up empty."""
        detail = await self._get(
            access_token, f"{API_BASE}/anime/{media_id}", {"fields": ANIME_DETAIL_FIELDS}
        )
        return parse_related_manga(detail)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_anime_parse.py -v`
Expected: PASS, 9 tests.

- [ ] **Step 6: Commit**

```bash
git add backend/app/providers/mal.py backend/tests/fixtures/mal_anime_page.json backend/tests/fixtures/mal_anime_detail.json backend/tests/test_anime_parse.py
git commit -m "feat(mal): read the anime list and its source manga"
```

---

### Task 4: The `ANIME_LIST_SYNC` job

**Files:**
- Create: `backend/app/handlers/anime_list_sync.py`
- Modify: `backend/app/settings_store.py`
- Modify: `backend/app/worker/main.py`
- Test: `backend/tests/test_anime_list_sync.py`

**Interfaces:**
- Consumes: `fetch_anime_list` / `fetch_related_manga` (Tasks 2-3), `JobContext` and `register` from `app.handlers.base`, `load_access_token` from `app.handlers.list_sync`.
- Produces:
  - `app.handlers.anime_list_sync.upsert_anime(session, dto) -> None`
  - `app.handlers.anime_list_sync.needs_mal_relations(session) -> list[str]`
  - `settings_store.CRON_ANIME_LIST_SYNC` with default `"0 */12 * * *"`
  - Job `JobType.ANIME_LIST_SYNC` with payload `{"provider": "anilist" | "mal"}`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_anime_list_sync.py
"""The anime mirror, against a real database.

The upsert has to be idempotent: the cron runs twice a day forever, and a second
row for the same anime would double every suggestion built from it.
"""

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import ListStatus, Provider
from app.handlers.anime_list_sync import needs_mal_relations, upsert_anime
from app.providers.base import AnimeEntryDTO, RelatedManga

pytestmark = pytest.mark.asyncio


def dto(*, media_id="21", status=ListStatus.COMPLETED, progress=24, related=None, provider=Provider.ANILIST):
    return AnimeEntryDTO(
        provider=provider,
        media_id=media_id,
        status=status,
        title_romaji="Vinland Saga",
        title_english="Vinland Saga",
        synonyms=["VS"],
        progress_episode=progress,
        total_episodes=24,
        cover_url="https://img/vs.jpg",
        related_manga=related if related is not None else [
            RelatedManga(provider=Provider.ANILIST, media_id="3000", relation="SOURCE",
                         title="Vinland Saga", format="MANGA")
        ],
        raw={"status": "COMPLETED"},
    )


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate anime_entry restart identity cascade"))
        await session.commit()
    yield


async def test_an_entry_is_stored_with_its_relations():
    async with get_sessionmaker()() as session:
        await upsert_anime(session, dto())
        await session.commit()
        row = (
            await session.execute(
                text("select status, progress_episode, related_manga from anime_entry")
            )
        ).one()
    assert row.status == "completed"
    assert row.progress_episode == 24
    assert row.related_manga[0]["media_id"] == "3000"


async def test_syncing_twice_updates_instead_of_duplicating():
    async with get_sessionmaker()() as session:
        await upsert_anime(session, dto())
        await upsert_anime(session, dto(progress=25))
        await session.commit()
        rows = (await session.execute(text("select progress_episode from anime_entry"))).all()
    assert [r.progress_episode for r in rows] == [25]


async def test_mal_entries_without_relations_are_the_ones_worth_a_detail_request():
    async with get_sessionmaker()() as session:
        await upsert_anime(session, dto(provider=Provider.MAL, media_id="99", related=[]))
        await upsert_anime(session, dto(provider=Provider.MAL, media_id="21"))
        await session.commit()
        pending = await needs_mal_relations(session)
    assert pending == ["99"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_anime_list_sync.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.handlers.anime_list_sync'`.

- [ ] **Step 3: Write the handler**

```python
# backend/app/handlers/anime_list_sync.py
"""Mirror the remote anime lists, relations included.

The relations are the whole point: they are what turns "I watched this" into
"there is a manga to read". AniList ships them inside the list query, so the
list costs one request. MyAnimeList only exposes them per anime, so that detail
is fetched exclusively for what AniList did not already answer.
"""

import json
from dataclasses import asdict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import JobType, Provider
from app.handlers.base import JobContext, register
from app.handlers.list_sync import load_access_token
from app.providers import get_source
from app.providers.base import AnimeEntryDTO


async def upsert_anime(session: AsyncSession, dto: AnimeEntryDTO) -> None:
    await session.execute(
        text(
            """
            insert into anime_entry (provider, provider_media_id, title_romaji, title_english,
                                     synonyms, status, progress_episode, total_episodes,
                                     cover_url, related_manga, raw, updated_at)
            values (:provider, :media_id, :romaji, :english, cast(:synonyms as jsonb), :status,
                    :progress, :total, :cover, cast(:related as jsonb), cast(:raw as jsonb), now())
            on conflict (provider, provider_media_id) do update
               set title_romaji = excluded.title_romaji,
                   title_english = excluded.title_english,
                   synonyms = excluded.synonyms,
                   status = excluded.status,
                   progress_episode = excluded.progress_episode,
                   total_episodes = excluded.total_episodes,
                   cover_url = excluded.cover_url,
                   related_manga = case
                       when jsonb_array_length(excluded.related_manga) > 0
                       then excluded.related_manga
                       else anime_entry.related_manga
                   end,
                   raw = excluded.raw,
                   updated_at = now()
            """
        ),
        {
            "provider": str(dto.provider),
            "media_id": dto.media_id,
            "romaji": dto.title_romaji,
            "english": dto.title_english,
            "synonyms": json.dumps(dto.synonyms),
            "status": str(dto.status),
            "progress": dto.progress_episode,
            "total": dto.total_episodes,
            "cover": dto.cover_url,
            "related": json.dumps(
                [{**asdict(r), "provider": str(r.provider)} for r in dto.related_manga]
            ),
            "raw": json.dumps(dto.raw or {}),
        },
    )


async def needs_mal_relations(session: AsyncSession) -> list[str]:
    """MyAnimeList anime with no relations stored yet, worth one detail request each."""
    result = await session.execute(
        text(
            """
            select provider_media_id from anime_entry
             where provider = 'mal'
               and jsonb_array_length(related_manga) = 0
               and status <> 'dropped'
             order by provider_media_id
            """
        )
    )
    return [row[0] for row in result.all()]


@register(JobType.ANIME_LIST_SYNC)
async def handle(ctx: JobContext) -> None:
    provider = Provider(ctx.payload["provider"])
    token = await load_access_token(ctx.session, provider)
    source = get_source(provider)

    await ctx.log(f"fetching {provider} anime list")
    entries = await source.fetch_anime_list(token)
    await ctx.log(f"{len(entries)} anime returned", pct=20)

    for dto in entries:
        await upsert_anime(ctx.session, dto)

    if provider is Provider.MAL:
        pending = await needs_mal_relations(ctx.session)
        for index, media_id in enumerate(pending, start=1):
            try:
                related = await source.fetch_related_manga(token, media_id)
            except Exception as exc:  # noqa: BLE001 - one dead title must not kill the sync
                await ctx.log(f"relations for {media_id} failed: {exc}", level="warning")
                continue
            if related:
                await ctx.session.execute(
                    text(
                        """
                        update anime_entry
                           set related_manga = cast(:related as jsonb), updated_at = now()
                         where provider = 'mal' and provider_media_id = :media_id
                        """
                    ),
                    {
                        "media_id": media_id,
                        "related": json.dumps(
                            [{**asdict(r), "provider": str(r.provider)} for r in related]
                        ),
                    },
                )
            if index % 20 == 0:
                await ctx.log(f"relations {index}/{len(pending)}")

    await ctx.enqueue(JobType.SUGGEST_BUILD, {}, dedupe_key="suggest_build")
    await ctx.log(f"done: {len(entries)} anime mirrored", pct=100)
```

- [ ] **Step 4: Add the cron setting**

In `backend/app/settings_store.py`: add the key constant, the default, the `_fallback` branch and the `all_settings` key list entry.

```python
CRON_ANIME_LIST_SYNC = "cron_anime_list_sync"
```

```python
    cron_anime_list_sync: str = "0 */12 * * *"
```

```python
        case k if k == CRON_ANIME_LIST_SYNC:
            return DEFAULTS.cron_anime_list_sync
```

- [ ] **Step 5: Register the handler and the cron in the worker**

In `backend/app/worker/main.py`: add `anime_list_sync`, `suggest_build` and `list_write` to the handler import block (they register by being imported; `suggest_build` and `list_write` arrive in Tasks 6 and 9 — add all three imports in Task 6 and Task 9 respectively, and only `anime_list_sync` now), then:

```python
async def enqueue_anime_list_sync() -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        for provider in Provider:
            await repo.enqueue(
                session,
                JobType.ANIME_LIST_SYNC,
                {"provider": str(provider)},
                dedupe_key=f"anime_list_sync:{provider}",
            )
        await session.commit()
    log.info("cron: queued anime list sync")
```

In `main()`, read `cron_anime = await settings_store.get(session, settings_store.CRON_ANIME_LIST_SYNC)` and register:

```python
    scheduler.add_job(
        enqueue_anime_list_sync, CronTrigger.from_crontab(cron_anime), id="anime_list_sync"
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_anime_list_sync.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 7: Commit**

```bash
git add backend/app/handlers/anime_list_sync.py backend/app/settings_store.py backend/app/worker/main.py backend/tests/test_anime_list_sync.py
git commit -m "feat(discovery): mirror the anime lists on a schedule"
```

---

### Task 5: Turn relations into ranked, deduplicated seeds

**Files:**
- Create: `backend/app/discovery/__init__.py`, `backend/app/discovery/seeds.py`
- Test: `backend/tests/test_discovery_seeds.py`

**Interfaces:**
- Consumes: `RelatedManga`, `ListStatus`, `Provider`, `app.text_utils.normalize`.
- Produces:
  - `Origin(provider, media_id, title, status, progress_episode, total_episodes)`
  - `Seed(provider, media_id, title, relation, origin, alt_ids: dict[str, str])`
  - `seeds_from(rows: list[AnimeRow]) -> list[Seed]` where `AnimeRow` is the duck-typed row from `anime_entry`
  - `collapse(seeds: list[Seed]) -> list[Seed]`
  - `beyond_signal(total_episodes: int | None, total_chapters: int | None) -> float`
  - `rank_score(*, anime_status: ListStatus, publishing_status: str | None, total_episodes: int | None, total_chapters: int | None) -> float`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_discovery_seeds.py
"""Pure suggestion logic: which relations become candidates, and in what order."""

from app.discovery.seeds import Origin, Seed, collapse, rank_score, seeds_from
from app.enums import ListStatus, Provider


class Row:
    """Stands in for a row of anime_entry."""

    def __init__(self, provider, media_id, status, related, total_episodes=24, progress=24):
        self.provider = provider
        self.provider_media_id = media_id
        self.status = status
        self.related_manga = related
        self.total_episodes = total_episodes
        self.progress_episode = progress
        self.title_english = "Vinland Saga"
        self.title_romaji = "Vinland Saga"


def relation(media_id="3000", provider="anilist", title="Vinland Saga"):
    return {"provider": provider, "media_id": media_id, "relation": "SOURCE",
            "title": title, "format": "MANGA"}


def test_a_dropped_anime_produces_nothing():
    rows = [Row("anilist", "21", "dropped", [relation()])]
    assert seeds_from(rows) == []


def test_a_relation_becomes_a_seed_carrying_its_origin():
    seed = seeds_from([Row("anilist", "21", "completed", [relation()])])[0]
    assert seed.provider is Provider.ANILIST
    assert seed.media_id == "3000"
    assert seed.origin.media_id == "21"
    assert seed.origin.status is ListStatus.COMPLETED


def test_the_same_manga_from_both_providers_collapses_onto_anilist():
    seeds = seeds_from(
        [
            Row("anilist", "21", "completed", [relation()]),
            Row("mal", "21", "completed", [relation(media_id="500", provider="mal")]),
        ]
    )
    collapsed = collapse(seeds)
    assert len(collapsed) == 1
    assert collapsed[0].provider is Provider.ANILIST
    assert collapsed[0].media_id == "3000"
    assert collapsed[0].alt_ids == {"mal": "500"}


def test_collapsing_keeps_the_strongest_anime_status_as_the_origin():
    """Watched to the end is a better reason to read than planning to watch."""
    seeds = seeds_from(
        [
            Row("anilist", "21", "plan_to_read", [relation()]),
            Row("mal", "21", "completed", [relation(media_id="500", provider="mal")]),
        ]
    )
    assert collapse(seeds)[0].origin.status is ListStatus.COMPLETED


def test_a_finished_anime_with_an_ongoing_manga_outranks_everything():
    assert rank_score(
        anime_status=ListStatus.COMPLETED, publishing_status="RELEASING",
        total_episodes=24, total_chapters=210,
    ) == 0.75


def test_a_watching_anime_scores_on_what_is_left_to_read():
    assert rank_score(
        anime_status=ListStatus.READING, publishing_status="FINISHED",
        total_episodes=12, total_chapters=30,
    ) == 0.41


def test_a_manga_the_anime_already_covered_gets_no_bonus():
    assert rank_score(
        anime_status=ListStatus.COMPLETED, publishing_status="FINISHED",
        total_episodes=24, total_chapters=36,
    ) == 0.30


def test_an_unknown_length_scores_on_the_status_alone():
    assert rank_score(
        anime_status=ListStatus.PLAN_TO_READ, publishing_status=None,
        total_episodes=None, total_chapters=None,
    ) == 0.10


def test_a_seed_is_hashable_so_dedupe_can_use_a_set():
    origin = Origin(Provider.MAL, "21", "V", ListStatus.COMPLETED, 24, 24)
    assert Seed(Provider.MAL, "1", "V", "SOURCE", origin) == Seed(
        Provider.MAL, "1", "V", "SOURCE", origin
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_discovery_seeds.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.discovery'`.

- [ ] **Step 3: Implement the module**

```python
# backend/app/discovery/seeds.py
"""From relations to ranked candidates. No database, no network.

Deduplication happens by normalised title rather than by id: the two providers
number the same manga differently, and the only thing they agree on is how it is
spelled. That is the same rule list_sync uses to merge entries into one series.
"""

from dataclasses import dataclass, field

from app.enums import ListStatus, Provider
from app.text_utils import normalize

# Roughly a chapter and a half per episode. Deliberately crude: this feeds a
# score and a sentence on a card, never a filter, so being wrong costs ordering.
CHAPTERS_PER_EPISODE = 1.5
BEYOND_CAP = 50
BEYOND_WEIGHT = 0.25

STATUS_WEIGHT = {
    ListStatus.READING: 0.35,
    ListStatus.ON_HOLD: 0.15,
    ListStatus.PLAN_TO_READ: 0.10,
}
STATUS_RANK = {
    ListStatus.COMPLETED: 4,
    ListStatus.READING: 3,
    ListStatus.ON_HOLD: 2,
    ListStatus.PLAN_TO_READ: 1,
    ListStatus.DROPPED: 0,
}


@dataclass(frozen=True)
class Origin:
    provider: Provider
    media_id: str
    title: str
    status: ListStatus
    progress_episode: int
    total_episodes: int | None


@dataclass(frozen=True)
class Seed:
    provider: Provider
    media_id: str
    title: str
    relation: str
    origin: Origin
    alt_ids: dict[str, str] = field(default_factory=dict)


def seeds_from(rows: list) -> list[Seed]:
    """One seed per manga relation on every anime worth suggesting from."""
    seeds: list[Seed] = []
    for row in rows:
        status = ListStatus(row.status)
        if status is ListStatus.DROPPED:
            continue
        origin = Origin(
            provider=Provider(row.provider),
            media_id=row.provider_media_id,
            title=row.title_english or row.title_romaji or "",
            status=status,
            progress_episode=row.progress_episode,
            total_episodes=row.total_episodes,
        )
        for related in row.related_manga or []:
            title = related.get("title") or ""
            if not title:
                continue
            seeds.append(
                Seed(
                    provider=Provider(related["provider"]),
                    media_id=str(related["media_id"]),
                    title=title,
                    relation=related.get("relation", ""),
                    origin=origin,
                )
            )
    return seeds


def collapse(seeds: list[Seed]) -> list[Seed]:
    """One seed per manga. AniList carries the identity; MyAnimeList rides along."""
    grouped: dict[str, list[Seed]] = {}
    for seed in seeds:
        grouped.setdefault(normalize(seed.title) or seed.title.casefold(), []).append(seed)

    collapsed: list[Seed] = []
    for group in grouped.values():
        primary = next(
            (s for s in group if s.provider is Provider.ANILIST),
            group[0],
        )
        alt_ids = {
            str(s.provider): s.media_id for s in group if s.provider is not primary.provider
        }
        best_origin = max(group, key=lambda s: STATUS_RANK.get(s.origin.status, 0)).origin
        collapsed.append(
            Seed(
                provider=primary.provider,
                media_id=primary.media_id,
                title=primary.title,
                relation=primary.relation,
                origin=best_origin,
                alt_ids=alt_ids,
            )
        )
    return collapsed


def beyond_signal(total_episodes: int | None, total_chapters: int | None) -> float:
    """How much story is left once the adaptation stops, as a 0..1 fraction of the cap."""
    if not total_episodes or not total_chapters:
        return 0.0
    adapted = round(total_episodes * CHAPTERS_PER_EPISODE)
    beyond = max(total_chapters - adapted, 0)
    return min(beyond / BEYOND_CAP, 1.0) * BEYOND_WEIGHT


def rank_score(
    *,
    anime_status: ListStatus,
    publishing_status: str | None,
    total_episodes: int | None,
    total_chapters: int | None,
) -> float:
    if anime_status is ListStatus.COMPLETED:
        base = 0.50 if publishing_status == "RELEASING" else 0.30
    else:
        base = STATUS_WEIGHT.get(anime_status, 0.10)
    return round(min(base + beyond_signal(total_episodes, total_chapters), 1.0), 4)
```

Create an empty `backend/app/discovery/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_discovery_seeds.py -v`
Expected: PASS, 9 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/discovery/__init__.py backend/app/discovery/seeds.py backend/tests/test_discovery_seeds.py
git commit -m "feat(discovery): rank and deduplicate manga relations"
```

---

### Task 6: The `SUGGEST_BUILD` job

**Files:**
- Create: `backend/app/handlers/suggest_build.py`
- Modify: `backend/app/providers/anilist.py` (metadata batch)
- Modify: `backend/app/worker/main.py` (import to register)
- Create: `backend/tests/fixtures/anilist_manga_meta.json`
- Test: `backend/tests/test_suggest_build.py`

**Interfaces:**
- Consumes: `seeds_from`, `collapse`, `rank_score` (Task 5); `anime_entry` rows (Task 4).
- Produces:
  - `app.providers.anilist.parse_manga_meta(data: dict) -> dict[str, MangaMeta]` keyed by AniList id
  - `MangaMeta(media_id, title, cover_url, total_chapters, year, publishing_status)` in `app/providers/base.py`
  - `AniListSource.fetch_manga_meta(access_token, ids: list[str]) -> dict[str, MangaMeta]`
  - `app.handlers.suggest_build.already_known(session) -> set[tuple[str, str]]`
  - `app.handlers.suggest_build.upsert_suggestion(session, seed, meta, score) -> None`

- [ ] **Step 1: Write the metadata fixture**

```json
// backend/tests/fixtures/anilist_manga_meta.json
{
  "Page": {
    "media": [
      {
        "id": 3000,
        "title": {"romaji": "Vinland Saga", "english": "Vinland Saga"},
        "coverImage": {"large": "https://img/vs-manga.jpg"},
        "chapters": 210,
        "status": "RELEASING",
        "startDate": {"year": 2005}
      },
      {
        "id": 4001,
        "title": {"romaji": "Mushoku Tensei", "english": "Jobless Reincarnation"},
        "coverImage": {"large": "https://img/mt-manga.jpg"},
        "chapters": null,
        "status": "RELEASING",
        "startDate": {"year": 2014}
      }
    ]
  }
}
```

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_suggest_build.py
"""Building suggestions: what is excluded, and what survives a rebuild."""

import json

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.discovery.seeds import Origin, Seed
from app.enums import ListStatus, Provider
from app.handlers.suggest_build import already_known, upsert_suggestion
from app.providers.anilist import parse_manga_meta

pytestmark = pytest.mark.asyncio

ORIGIN = Origin(Provider.ANILIST, "21", "Vinland Saga", ListStatus.COMPLETED, 24, 24)
SEED = Seed(Provider.ANILIST, "3000", "Vinland Saga", "SOURCE", ORIGIN, {"mal": "500"})


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(
            text("truncate suggestion, anime_entry, list_entry, series restart identity cascade")
        )
        await session.commit()
    yield


def test_manga_metadata_is_keyed_by_id_and_keeps_a_missing_count_as_none(fixture):
    meta = parse_manga_meta(fixture("anilist_manga_meta.json"))
    assert meta["3000"].total_chapters == 210
    assert meta["3000"].publishing_status == "RELEASING"
    assert meta["3000"].year == 2005
    assert meta["4001"].total_chapters is None


async def test_a_manga_already_on_the_reading_list_is_known(fixture):
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into list_entry (provider, provider_media_id, status, synonyms, raw,
                                        updated_at)
                values ('anilist', '3000', 'reading', '[]'::jsonb, '{}'::jsonb, now())
                """
            )
        )
        await session.commit()
        known = await already_known(session)
    assert ("anilist", "3000") in known


async def test_a_suggestion_is_written_with_its_reason(fixture):
    meta = parse_manga_meta(fixture("anilist_manga_meta.json"))["3000"]
    async with get_sessionmaker()() as session:
        await upsert_suggestion(session, SEED, meta, 0.75)
        await session.commit()
        row = (
            await session.execute(
                text("select title, rank_score, alt_ids, meta, state from suggestion")
            )
        ).one()
    assert row.title == "Vinland Saga"
    assert float(row.rank_score) == 0.75
    assert row.alt_ids == {"mal": "500"}
    assert row.meta["origin"]["title"] == "Vinland Saga"
    assert row.state == "new"


async def test_rebuilding_never_resurrects_a_dismissed_suggestion(fixture):
    meta = parse_manga_meta(fixture("anilist_manga_meta.json"))["3000"]
    async with get_sessionmaker()() as session:
        await upsert_suggestion(session, SEED, meta, 0.75)
        await session.execute(text("update suggestion set state = 'dismissed'"))
        await session.commit()
        await upsert_suggestion(session, SEED, meta, 0.80)
        await session.commit()
        row = (await session.execute(text("select state, rank_score from suggestion"))).one()
    assert row.state == "dismissed"
    assert float(row.rank_score) == 0.80
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_suggest_build.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_manga_meta'`.

- [ ] **Step 4: Add `MangaMeta` and the AniList batch query**

In `backend/app/providers/base.py`:

```python
@dataclass(frozen=True)
class MangaMeta:
    media_id: str
    title: str
    cover_url: str | None = None
    total_chapters: int | None = None
    year: int | None = None
    publishing_status: str | None = None
```

In `backend/app/providers/anilist.py`:

```python
META_PAGE = 50

MANGA_META_QUERY = """
query ($ids: [Int]) {
  Page(perPage: 50) {
    media(id_in: $ids, type: MANGA) {
      id
      title { romaji english }
      coverImage { large }
      chapters
      status
      startDate { year }
    }
  }
}
"""


def parse_manga_meta(data: dict[str, Any]) -> dict[str, MangaMeta]:
    """Pure parser: id to metadata, for the suggestion cards."""
    meta: dict[str, MangaMeta] = {}
    for media in (data.get("Page") or {}).get("media", []) or []:
        title = media.get("title") or {}
        media_id = str(media.get("id"))
        meta[media_id] = MangaMeta(
            media_id=media_id,
            title=title.get("english") or title.get("romaji") or "",
            cover_url=(media.get("coverImage") or {}).get("large"),
            total_chapters=media.get("chapters"),
            year=(media.get("startDate") or {}).get("year"),
            publishing_status=media.get("status"),
        )
    return meta
```

```python
    async def fetch_manga_meta(self, access_token: str, ids: list[str]) -> dict[str, MangaMeta]:
        """Batched: AniList allows about 90 requests a minute, and lists run long."""
        collected: dict[str, MangaMeta] = {}
        numeric = [int(i) for i in ids if str(i).isdigit()]
        for start in range(0, len(numeric), META_PAGE):
            data = await self._post(
                access_token, MANGA_META_QUERY, {"ids": numeric[start : start + META_PAGE]}
            )
            collected.update(parse_manga_meta(data))
        return collected
```

- [ ] **Step 5: Write the handler**

```python
# backend/app/handlers/suggest_build.py
"""Turn the anime mirror into suggestions.

The state of an existing suggestion is never touched here. Rebuilding refreshes
what the card shows and how it ranks; whether the user already answered it is the
user's decision, and a cron does not get to undo it.
"""

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.discovery.seeds import Seed, collapse, rank_score, seeds_from
from app.enums import JobType, Provider
from app.handlers.base import JobContext, register
from app.handlers.list_sync import load_access_token
from app.providers import get_source
from app.providers.base import MangaMeta
from app.text_utils import normalize


async def anime_rows(session: AsyncSession) -> list:
    result = await session.execute(
        text(
            """
            select provider, provider_media_id, status, progress_episode, total_episodes,
                   title_english, title_romaji, related_manga
              from anime_entry
             where status <> 'dropped'
            """
        )
    )
    return result.all()


async def already_known(session: AsyncSession) -> set[tuple[str, str]]:
    """Manga ids already on a reading list. Suggesting those is noise."""
    result = await session.execute(
        text("select provider, provider_media_id from list_entry")
    )
    return {(row.provider, row.provider_media_id) for row in result.all()}


async def already_a_series(session: AsyncSession, title: str) -> bool:
    alias = normalize(title)
    if not alias:
        return False
    result = await session.execute(
        text(
            """
            select 1 from series
             where jsonb_exists(meta -> 'aliases', :alias)
             limit 1
            """
        ),
        {"alias": alias},
    )
    return result.first() is not None


async def upsert_suggestion(
    session: AsyncSession, seed: Seed, meta: MangaMeta | None, score: float
) -> None:
    await session.execute(
        text(
            """
            insert into suggestion (provider, provider_media_id, alt_ids, title, cover_url,
                                    total_chapters, year, publishing_status, rank_score, meta,
                                    created_at, updated_at)
            values (:provider, :media_id, cast(:alt_ids as jsonb), :title, :cover, :chapters,
                    :year, :publishing, :score, cast(:meta as jsonb), now(), now())
            on conflict (provider, provider_media_id) do update
               set alt_ids = excluded.alt_ids,
                   title = excluded.title,
                   cover_url = excluded.cover_url,
                   total_chapters = excluded.total_chapters,
                   year = excluded.year,
                   publishing_status = excluded.publishing_status,
                   rank_score = excluded.rank_score,
                   meta = suggestion.meta || excluded.meta,
                   updated_at = now()
            """
        ),
        {
            "provider": str(seed.provider),
            "media_id": seed.media_id,
            "alt_ids": json.dumps(seed.alt_ids),
            "title": (meta.title if meta and meta.title else seed.title)[:500],
            "cover": meta.cover_url if meta else None,
            "chapters": meta.total_chapters if meta else None,
            "year": meta.year if meta else None,
            "publishing": meta.publishing_status if meta else None,
            "score": score,
            "meta": json.dumps(
                {
                    "relation": seed.relation,
                    "origin": {
                        "provider": str(seed.origin.provider),
                        "media_id": seed.origin.media_id,
                        "title": seed.origin.title,
                        "status": str(seed.origin.status),
                        "progress_episode": seed.origin.progress_episode,
                        "total_episodes": seed.origin.total_episodes,
                    },
                }
            ),
        },
    )


@register(JobType.SUGGEST_BUILD)
async def handle(ctx: JobContext) -> None:
    rows = await anime_rows(ctx.session)
    seeds = collapse(seeds_from(rows))
    await ctx.log(f"{len(seeds)} manga relations across {len(rows)} anime", pct=20)

    known = await already_known(ctx.session)
    wanted: list[Seed] = []
    for seed in seeds:
        ids = {(str(seed.provider), seed.media_id)} | {
            (provider, media_id) for provider, media_id in seed.alt_ids.items()
        }
        if ids & known:
            continue
        if await already_a_series(ctx.session, seed.title):
            continue
        wanted.append(seed)
    await ctx.log(f"{len(wanted)} not already on a list", pct=40)

    meta: dict[str, MangaMeta] = {}
    anilist_ids = [s.media_id for s in wanted if s.provider is Provider.ANILIST]
    if anilist_ids:
        try:
            token = await load_access_token(ctx.session, Provider.ANILIST)
            meta = await get_source(Provider.ANILIST).fetch_manga_meta(token, anilist_ids)
        except Exception as exc:  # noqa: BLE001 - a card without metadata still beats no card
            await ctx.log(f"metadata fetch failed: {exc}", level="warning")

    for seed in wanted:
        entry = meta.get(seed.media_id)
        score = rank_score(
            anime_status=seed.origin.status,
            publishing_status=entry.publishing_status if entry else None,
            total_episodes=seed.origin.total_episodes,
            total_chapters=entry.total_chapters if entry else None,
        )
        await upsert_suggestion(ctx.session, seed, entry, score)

    await ctx.log(f"done: {len(wanted)} suggestions", pct=100)
```

Add `suggest_build` to the handler import block in `backend/app/worker/main.py`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_suggest_build.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 7: Commit**

```bash
git add backend/app/handlers/suggest_build.py backend/app/providers/base.py backend/app/providers/anilist.py backend/app/worker/main.py backend/tests/fixtures/anilist_manga_meta.json backend/tests/test_suggest_build.py
git commit -m "feat(discovery): build suggestions from the anime relations"
```

---

### Task 7: The comick client and its sources

**Files:**
- Create: `backend/app/sources/comick_client.py`, `backend/app/sources/comick.py`
- Modify: `backend/app/sources/__init__.py`, `backend/app/config.py`, `docker-compose.yml`, `.env.example`
- Create: `backend/tests/fixtures/comick_search.json`, `backend/tests/fixtures/comick_chapters.json`
- Test: `backend/tests/test_comick_parse.py`

**Interfaces:**
- Consumes: `Candidate`, `ChapterRef`, `Source`, `register` from `app.sources.base`; `best_similarity` from `app.text_utils`.
- Produces:
  - `parse_search(payload: dict, titles: list[str], *, site: str) -> list[Candidate]`
  - `parse_chapters(payload: dict) -> list[ChapterRef]`
  - `ComickClient(base_url, client=None)` with `search`, `chapters`, `health`
  - Registered sources `asurascan` and `weebcentral`
  - `Settings.comick_api_url` (default `http://comick:3000`)

- [ ] **Step 1: Write the fixtures**

```json
// backend/tests/fixtures/comick_search.json
{
  "results": [
    {
      "source": "asurascan",
      "manga": [
        {
          "id": "vinland-saga",
          "title": "Vinland Saga",
          "url": "https://asuracomic.net/series/vinland-saga",
          "coverImage": "https://asura/cover.jpg",
          "latestChapter": 210,
          "lastUpdated": "2026-08-01"
        },
        {
          "id": "vinland-saga-side",
          "title": "Vinland Saga Side Story",
          "url": "https://asuracomic.net/series/vinland-saga-side",
          "coverImage": null,
          "latestChapter": 0,
          "lastUpdated": "2026-01-01"
        }
      ]
    }
  ]
}
```

```json
// backend/tests/fixtures/comick_chapters.json
{
  "source": "asurascan",
  "totalChapters": 3,
  "chapters": [
    {"id": "c1", "number": 1, "title": "Normandy", "url": "https://asuracomic.net/series/vs/chapter/1"},
    {"id": "c2", "number": 2.5, "title": null, "url": "https://asuracomic.net/series/vs/chapter/2-5"},
    {"id": "c3", "number": 0, "title": "Prologue", "url": "https://asuracomic.net/series/vs/chapter/prologue"}
  ]
}
```

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_comick_parse.py
from decimal import Decimal

from app.sources import source_for_url
from app.sources.comick_client import parse_chapters, parse_search


def test_search_scores_the_exact_title_above_a_side_story(fixture):
    candidates = parse_search(fixture("comick_search.json"), ["Vinland Saga"], site="asurascan")
    assert candidates[0].title == "Vinland Saga"
    assert candidates[0].score > candidates[1].score


def test_search_carries_the_site_and_the_chapter_count(fixture):
    candidate = parse_search(fixture("comick_search.json"), ["Vinland Saga"], site="asurascan")[0]
    assert candidate.source_site == "asurascan"
    assert candidate.source_url == "https://asuracomic.net/series/vinland-saga"
    assert candidate.chapter_count == 210


def test_a_zero_latest_chapter_is_absence_not_a_count(fixture):
    """The pipeline types this as a nullable integer; zero would read as a real answer."""
    candidates = parse_search(fixture("comick_search.json"), ["Vinland Saga"], site="asurascan")
    side = next(c for c in candidates if c.title.endswith("Side Story"))
    assert side.chapter_count is None


def test_chapters_are_read_as_decimals_including_fractions(fixture):
    numbers = [c.number for c in parse_chapters(fixture("comick_chapters.json"))]
    assert Decimal("2.5") in numbers


def test_an_unnumbered_prologue_is_skipped(fixture):
    """Chapter zero has no place in a download range the binary understands."""
    chapters = parse_chapters(fixture("comick_chapters.json"))
    assert [str(c.number) for c in chapters] == ["1", "2.5"]


def test_an_asura_url_resolves_to_the_registered_source():
    assert source_for_url("https://asuracomic.net/series/vinland-saga").site == "asurascan"


def test_a_weebcentral_url_resolves_to_the_registered_source():
    assert source_for_url("https://weebcentral.com/series/abc").site == "weebcentral"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_comick_parse.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.sources.comick_client'`.

- [ ] **Step 4: Write the client**

```python
# backend/app/sources/comick_client.py
"""Client for comick-source-api, which scrapes many sites behind one JSON API.

It answers where a manga lives and which chapters exist. It never returns page
images — there is no endpoint for them — so downloading stays with the binary,
which already supports the sites registered here.
"""

from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.config import get_settings
from app.sources.base import Candidate, ChapterRef
from app.text_utils import best_similarity


def _to_int(value: Any) -> int | None:
    try:
        number = int(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number or None


def parse_search(payload: dict[str, Any], titles: list[str], *, site: str) -> list[Candidate]:
    """Pure parser and ranker for one multi-source search response."""
    candidates: list[Candidate] = []
    for group in payload.get("results", []) or []:
        if group.get("source") != site:
            continue
        for manga in group.get("manga", []) or []:
            title = manga.get("title") or ""
            url = manga.get("url")
            if not title or not url:
                continue
            score = max(best_similarity([title], t) for t in titles) if titles else 0.0
            candidates.append(
                Candidate(
                    source_site=site,
                    source_url=url,
                    title=title,
                    cover_url=manga.get("coverImage"),
                    chapter_count=_to_int(manga.get("latestChapter")),
                    score=round(score, 4),
                )
            )
    return sorted(candidates, key=lambda c: c.score, reverse=True)


def parse_chapters(payload: dict[str, Any]) -> list[ChapterRef]:
    chapters: list[ChapterRef] = []
    for item in payload.get("chapters", []) or []:
        raw_number = item.get("number")
        try:
            number = Decimal(str(raw_number))
        except (InvalidOperation, ValueError, TypeError):
            continue
        if number <= 0:
            continue  # prologues and specials have no place in a chapter range
        chapters.append(
            ChapterRef(
                number=number,
                url=item.get("url") or "",
                title=item.get("title") or None,
            )
        )
    return sorted(chapters, key=lambda c: c.number)


class ComickClient:
    def __init__(self, base_url: str | None = None, client: httpx.AsyncClient | None = None):
        self._base_url = (base_url or get_settings().comick_api_url).rstrip("/")
        self._client = client

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        if self._client is not None:
            response = await self._client.post(f"{self._base_url}{path}", json=body)
        else:
            async with httpx.AsyncClient(timeout=30) as owned:
                response = await owned.post(f"{self._base_url}{path}", json=body)
        response.raise_for_status()
        return response.json()

    async def search(self, query: str, sources: list[str]) -> dict[str, Any]:
        return await self._post("/api/search", {"query": query, "sources": sources})

    async def chapters(self, url: str, source: str) -> dict[str, Any]:
        return await self._post("/api/chapters", {"url": url, "source": source})

    async def health(self) -> bool:
        try:
            if self._client is not None:
                response = await self._client.get(f"{self._base_url}/api/health")
            else:
                async with httpx.AsyncClient(timeout=10) as owned:
                    response = await owned.get(f"{self._base_url}/api/health")
            return response.status_code < 400
        except httpx.HTTPError:
            return False
```

- [ ] **Step 5: Register the sources**

```python
# backend/app/sources/comick.py
"""Sites reachable through comick, restricted to those the binary can download.

Adding a site is one entry in SITES, and it only belongs there once the download
binary lists its domain — a candidate that cannot be fetched is a dead end on the
review screen.
"""

import httpx

from app.sources.base import Candidate, ChapterRef, Source, register
from app.sources.comick_client import ComickClient, parse_chapters, parse_search

SITES = (
    ("asurascan", ("asuracomic.net", "asurascans.com", "asuratoon.com")),
    ("weebcentral", ("weebcentral.com",)),
)


class ComickSource(Source):
    """One registered site, served by the shared comick API."""

    def __init__(self, site: str, domains: tuple[str, ...],
                 client: httpx.AsyncClient | None = None) -> None:
        self.site = site
        self.domains = domains
        self._api = ComickClient(client=client)

    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]:
        if not titles:
            return []
        payload = await self._api.search(titles[0], [self.site])
        return parse_search(payload, titles, site=self.site)[:limit]

    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        payload = await self._api.chapters(url, self.site)
        return parse_chapters(payload)


for site, domains in SITES:
    register(ComickSource(site, domains))
```

Import it from `backend/app/sources/__init__.py` next to `mangadex` so registration happens:

```python
from app.sources import comick, mangadex  # noqa: F401
```

Add to `backend/app/config.py`:

```python
    comick_api_url: str = "http://comick:3000"
```

Add the service to `docker-compose.yml`, next to the other services (match the file's existing indentation and network/restart conventions):

```yaml
  comick:
    build:
      context: https://github.com/GooglyBlox/comick-source-api.git
    restart: unless-stopped
    expose:
      - "3000"
```

Add `COMICK_API_URL=http://comick:3000` to `.env.example` under a short comment saying it points at the bundled scraper API.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_comick_parse.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 7: Verify the existing source tests still pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_sources_parse.py -v`
Expected: PASS — registering new sources must not disturb MangaDex resolution.

- [ ] **Step 8: Commit**

```bash
git add backend/app/sources/comick_client.py backend/app/sources/comick.py backend/app/sources/__init__.py backend/app/config.py docker-compose.yml .env.example backend/tests/fixtures/comick_search.json backend/tests/fixtures/comick_chapters.json backend/tests/test_comick_parse.py
git commit -m "feat(sources): reach asura and weebcentral through comick"
```

---

### Task 8: Attach sources and the MangaDex id to each suggestion

**Files:**
- Modify: `backend/app/handlers/suggest_build.py`
- Modify: `backend/app/sources/mangadex.py`
- Test: `backend/tests/test_suggest_build.py` (append)

**Interfaces:**
- Consumes: `all_sources()` (Task 7 registers two more), `Candidate`.
- Produces:
  - `app.sources.mangadex.manga_id_from_candidate(candidate: Candidate) -> str | None`
  - `app.handlers.suggest_build.source_summary(candidates: list[Candidate]) -> dict` returning `{"sources": [...], "mangadex_uuid": str | None, "best": {...} | None}`

- [ ] **Step 1: Write the failing test (append to `tests/test_suggest_build.py`)**

```python
from app.handlers.suggest_build import source_summary
from app.sources.base import Candidate


def candidate(site, url, score, chapters=100):
    return Candidate(source_site=site, source_url=url, title="Vinland Saga",
                     chapter_count=chapters, score=score)


def test_the_summary_keeps_every_site_that_answered():
    summary = source_summary(
        [
            candidate("asurascan", "https://asuracomic.net/series/vs", 0.90),
            candidate("mangadex", "https://mangadex.org/title/uuid-1", 0.88),
        ]
    )
    assert {s["site"] for s in summary["sources"]} == {"asurascan", "mangadex"}


def test_mangadex_wins_a_close_call_because_its_numbering_can_be_trusted():
    summary = source_summary(
        [
            candidate("asurascan", "https://asuracomic.net/series/vs", 0.90),
            candidate("mangadex", "https://mangadex.org/title/uuid-1", 0.88),
        ]
    )
    assert summary["best"]["site"] == "mangadex"


def test_a_clearly_better_match_elsewhere_still_wins():
    summary = source_summary(
        [
            candidate("asurascan", "https://asuracomic.net/series/vs", 0.95),
            candidate("mangadex", "https://mangadex.org/title/uuid-1", 0.60),
        ]
    )
    assert summary["best"]["site"] == "asurascan"


def test_the_mangadex_uuid_is_kept_even_when_another_site_is_preferred():
    """Writing the MangaDex reading status needs the uuid, whatever we download from."""
    summary = source_summary(
        [
            candidate("asurascan", "https://asuracomic.net/series/vs", 0.95),
            candidate("mangadex", "https://mangadex.org/title/uuid-1", 0.60),
        ]
    )
    assert summary["mangadex_uuid"] == "uuid-1"


def test_no_candidates_means_no_best_and_no_uuid():
    assert source_summary([]) == {"sources": [], "mangadex_uuid": None, "best": None}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_suggest_build.py -v`
Expected: FAIL — `ImportError: cannot import name 'source_summary'`.

- [ ] **Step 3: Implement**

In `backend/app/sources/mangadex.py`:

```python
def manga_id_from_candidate(candidate: Candidate) -> str | None:
    """The uuid behind a MangaDex candidate, or None for any other site."""
    if candidate.source_site != SITE:
        return None
    try:
        return manga_id_from_url(candidate.source_url)
    except ValueError:
        return None
```

In `backend/app/handlers/suggest_build.py`, extend the imports with `from typing import Any`, `from app.sources import Candidate, all_sources` and `from app.sources.mangadex import manga_id_from_candidate`, then add:

```python
# MangaDex publishes a documented API, numbers its chapters reliably and holds the
# personal login, so it only loses the tie-break when another site matches clearly
# better rather than marginally.
MANGADEX_EDGE = 0.05


def source_summary(candidates: list[Candidate]) -> dict[str, Any]:
    summary = [
        {
            "site": c.source_site,
            "url": c.source_url,
            "chapters": c.chapter_count,
            "score": float(c.score),
        }
        for c in sorted(candidates, key=lambda c: c.score, reverse=True)
    ]
    uuid = next(
        (manga_id_from_candidate(c) for c in candidates if manga_id_from_candidate(c)), None
    )
    best = None
    if summary:
        ranked = sorted(
            candidates,
            key=lambda c: c.score + (MANGADEX_EDGE if c.source_site == "mangadex" else 0.0),
            reverse=True,
        )
        winner = ranked[0]
        best = {
            "site": winner.source_site,
            "url": winner.source_url,
            "score": float(winner.score),
        }
    return {"sources": summary, "mangadex_uuid": uuid, "best": best}
```

In the `SUGGEST_BUILD` handler, after computing `score` for a seed and before `upsert_suggestion`, gather candidates and merge the summary into the stored meta:

```python
        candidates: list[Candidate] = []
        for source in all_sources():
            try:
                candidates.extend(await source.search([seed.title], limit=5))
            except Exception as exc:  # noqa: BLE001 - a dead site must not stop the build
                await ctx.log(f"{source.site} search failed: {exc}", level="warning")
        await upsert_suggestion(ctx.session, seed, entry, score, source_summary(candidates))
```

Extend `upsert_suggestion` with a `sources: dict[str, Any] | None = None` parameter whose content is merged into the `meta` json (`{**base_meta, **(sources or {})}`). The `meta = suggestion.meta || excluded.meta` merge already preserves keys the rebuild does not set.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_suggest_build.py -v`
Expected: PASS, 9 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/handlers/suggest_build.py backend/app/sources/mangadex.py backend/tests/test_suggest_build.py
git commit -m "feat(discovery): record where each suggested manga can be read"
```

---

### Task 9: Status mapping and the `LIST_WRITE` job

**Files:**
- Create: `backend/app/discovery/status_sync.py`, `backend/app/handlers/list_write.py`
- Modify: `backend/app/providers/anilist.py`, `backend/app/providers/mal.py`, `backend/app/sources/mangadex.py`, `backend/app/worker/main.py`
- Test: `backend/tests/test_status_sync.py`, `backend/tests/test_list_write.py`

**Interfaces:**
- Consumes: `ListStatus`; `suggestion` rows with `meta.mangadex_uuid` and `alt_ids` (Tasks 6 and 8).
- Produces:
  - `mal_status(status) -> str`, `anilist_status(status) -> str`, `mangadex_status(status) -> str`
  - `AniListSource.set_status`, `MyAnimeListSource.set_status`, `MangaDexSource.set_reading_status(manga_id, status)`
  - `app.handlers.list_write.targets_for(row) -> list[tuple[str, str]]` as `(target, media_id)`
  - `app.handlers.list_write.pending_targets(row) -> list[tuple[str, str]]` skipping targets already recorded ok
  - Job `JobType.LIST_WRITE` with payload `{"suggestion_id": int, "status": "reading"}`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_status_sync.py
import pytest

from app.discovery.status_sync import anilist_status, mal_status, mangadex_status
from app.enums import ListStatus


@pytest.mark.parametrize(
    "status,mal,anilist,mangadex",
    [
        (ListStatus.READING, "reading", "CURRENT", "reading"),
        (ListStatus.PLAN_TO_READ, "plan_to_read", "PLANNING", "plan_to_read"),
        (ListStatus.COMPLETED, "completed", "COMPLETED", "completed"),
        (ListStatus.ON_HOLD, "on_hold", "PAUSED", "on_hold"),
        (ListStatus.DROPPED, "dropped", "DROPPED", "dropped"),
    ],
)
def test_every_status_has_a_word_in_every_dialect(status, mal, anilist, mangadex):
    assert mal_status(status) == mal
    assert anilist_status(status) == anilist
    assert mangadex_status(status) == mangadex
```

```python
# backend/tests/test_list_write.py
"""Writing the chosen status outward, one independent target at a time."""

import json

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.handlers.list_write import pending_targets, record_result, targets_for

pytestmark = pytest.mark.asyncio


class Row:
    def __init__(self, provider="anilist", media_id="3000", alt_ids=None, meta=None):
        self.provider = provider
        self.provider_media_id = media_id
        self.alt_ids = alt_ids or {}
        self.meta = meta or {}


def test_a_suggestion_known_to_both_providers_writes_to_both():
    row = Row(alt_ids={"mal": "500"}, meta={"mangadex_uuid": "uuid-1"})
    assert targets_for(row) == [("anilist", "3000"), ("mal", "500"), ("mangadex", "uuid-1")]


def test_a_suggestion_without_a_mangadex_match_simply_has_no_such_target():
    assert targets_for(Row()) == [("anilist", "3000")]


def test_a_retry_only_repeats_the_targets_that_failed():
    row = Row(
        alt_ids={"mal": "500"},
        meta={
            "mangadex_uuid": "uuid-1",
            "write_results": [
                {"target": "anilist", "ok": True},
                {"target": "mal", "ok": False, "error": "500 from mal"},
            ],
        },
    )
    assert pending_targets(row) == [("mal", "500"), ("mangadex", "uuid-1")]


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate suggestion restart identity cascade"))
        await session.commit()
    yield


async def test_results_accumulate_on_the_suggestion():
    async with get_sessionmaker()() as session:
        suggestion_id = (
            await session.execute(
                text(
                    """
                    insert into suggestion (provider, provider_media_id, title, alt_ids, meta)
                    values ('anilist', '3000', 'V', '{}'::jsonb, '{}'::jsonb) returning id
                    """
                )
            )
        ).scalar_one()
        await record_result(session, suggestion_id, "anilist", ok=True, error=None)
        await record_result(session, suggestion_id, "mal", ok=False, error="boom")
        await session.commit()
        meta = (
            await session.execute(
                text("select meta from suggestion where id = :id"), {"id": suggestion_id}
            )
        ).scalar_one()
    results = {r["target"]: r for r in meta["write_results"]}
    assert results["anilist"]["ok"] is True
    assert results["mal"]["error"] == "boom"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_status_sync.py tests/test_list_write.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.discovery.status_sync'`.

- [ ] **Step 3: Write the status map**

```python
# backend/app/discovery/status_sync.py
"""One internal status, four dialects.

Keeping the translation in one pure module is what makes "the same status
everywhere" checkable in a test rather than asserted in a comment.
"""

from app.enums import ListStatus

MAL = {
    ListStatus.READING: "reading",
    ListStatus.PLAN_TO_READ: "plan_to_read",
    ListStatus.COMPLETED: "completed",
    ListStatus.ON_HOLD: "on_hold",
    ListStatus.DROPPED: "dropped",
}

ANILIST = {
    ListStatus.READING: "CURRENT",
    ListStatus.PLAN_TO_READ: "PLANNING",
    ListStatus.COMPLETED: "COMPLETED",
    ListStatus.ON_HOLD: "PAUSED",
    ListStatus.DROPPED: "DROPPED",
}

# MangaDex happens to use the same words as MyAnimeList, but they are separate
# contracts: one of them changing must not silently change the other.
MANGADEX = {
    ListStatus.READING: "reading",
    ListStatus.PLAN_TO_READ: "plan_to_read",
    ListStatus.COMPLETED: "completed",
    ListStatus.ON_HOLD: "on_hold",
    ListStatus.DROPPED: "dropped",
}


def mal_status(status: ListStatus) -> str:
    return MAL[status]


def anilist_status(status: ListStatus) -> str:
    return ANILIST[status]


def mangadex_status(status: ListStatus) -> str:
    return MANGADEX[status]
```

- [ ] **Step 4: Add the write calls to the providers**

In `anilist.py`:

```python
STATUS_MUTATION = """
mutation ($mediaId: Int, $status: MediaListStatus) {
  SaveMediaListEntry(mediaId: $mediaId, status: $status) { id status }
}
"""
```

```python
    async def set_status(self, access_token: str, media_id: str, status: ListStatus) -> None:
        await self._post(
            access_token,
            STATUS_MUTATION,
            {"mediaId": int(media_id), "status": anilist_status(status)},
        )
```

In `mal.py`:

```python
    async def set_status(self, access_token: str, media_id: str, status: ListStatus) -> None:
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"{API_BASE}/manga/{media_id}/my_list_status"
        data = {"status": mal_status(status)}
        if self._client is not None:
            response = await self._client.patch(url, data=data, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.patch(url, data=data, headers=headers)
        response.raise_for_status()
```

In `mangadex.py`, on `MangaDexSource`:

```python
    async def set_reading_status(self, manga_id: str, status: ListStatus) -> None:
        """Follow-list status. This is one of the few endpoints that needs the login."""
        token = await tokens.token(self._client)
        if not token:
            raise RuntimeError("mangadex credentials are not configured")
        headers = {"Authorization": f"Bearer {token}"}
        body = {"status": mangadex_status(status)}
        url = f"{API_BASE}/manga/{manga_id}/status"
        if self._client is not None:
            response = await self._client.post(url, json=body, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(url, json=body, headers=headers)
        response.raise_for_status()
```

- [ ] **Step 5: Write the handler**

```python
# backend/app/handlers/list_write.py
"""Write the chosen status to every place that keeps a list.

Three external services fail independently, so each is recorded independently
and a retry repeats only what did not land. Writing a status is idempotent, which
is what makes repeating it free.
"""

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.discovery.status_sync import mangadex_status  # noqa: F401 - documents the contract
from app.enums import JobType, ListStatus, Provider
from app.handlers.base import JobContext, PermanentError, register
from app.handlers.list_sync import load_access_token
from app.providers import get_source
from app.providers.tokens import NotConnected
from app.sources import get_source as get_site


def targets_for(row: Any) -> list[tuple[str, str]]:
    """Every list that can hold this manga, in a stable order."""
    targets: list[tuple[str, str]] = [(row.provider, row.provider_media_id)]
    for provider, media_id in (row.alt_ids or {}).items():
        targets.append((provider, media_id))
    uuid = (row.meta or {}).get("mangadex_uuid")
    if uuid:
        targets.append(("mangadex", uuid))
    return targets


def pending_targets(row: Any) -> list[tuple[str, str]]:
    done = {
        result["target"]
        for result in (row.meta or {}).get("write_results", [])
        if result.get("ok")
    }
    return [target for target in targets_for(row) if target[0] not in done]


async def record_result(
    session: AsyncSession, suggestion_id: int, target: str, *, ok: bool, error: str | None
) -> None:
    await session.execute(
        text(
            """
            update suggestion
               set meta = jsonb_set(
                       coalesce(meta, '{}'::jsonb),
                       '{write_results}',
                       (
                         select coalesce(jsonb_agg(entry), '[]'::jsonb)
                           from jsonb_array_elements(
                                    coalesce(meta -> 'write_results', '[]'::jsonb)
                                ) as entry
                          where entry ->> 'target' <> :target
                       ) || cast(:result as jsonb)
                   ),
                   updated_at = now()
             where id = :id
            """
        ),
        {
            "id": suggestion_id,
            "target": target,
            "result": json.dumps([{"target": target, "ok": ok, "error": error}]),
        },
    )


async def load_suggestion(session: AsyncSession, suggestion_id: int) -> Any:
    result = await session.execute(
        text(
            """
            select id, provider, provider_media_id, alt_ids, meta
              from suggestion where id = :id
            """
        ),
        {"id": suggestion_id},
    )
    row = result.first()
    if row is None:
        raise PermanentError(f"suggestion {suggestion_id} no longer exists")
    return row


@register(JobType.LIST_WRITE)
async def handle(ctx: JobContext) -> None:
    suggestion_id = int(ctx.payload["suggestion_id"])
    status = ListStatus(ctx.payload["status"])
    row = await load_suggestion(ctx.session, suggestion_id)

    pending = pending_targets(row)
    if not pending:
        await ctx.log("every list already carries this status", pct=100)
        return

    failures: list[str] = []
    for target, media_id in pending:
        try:
            if target == "mangadex":
                await get_site("mangadex").set_reading_status(media_id, status)
            else:
                provider = Provider(target)
                token = await load_access_token(ctx.session, provider)
                await get_source(provider).set_status(token, media_id, status)
        except NotConnected as exc:
            await record_result(ctx.session, suggestion_id, target, ok=False, error=str(exc))
            raise PermanentError(f"{target} is not connected") from exc
        except Exception as exc:  # noqa: BLE001 - one target's failure is not the others'
            await record_result(ctx.session, suggestion_id, target, ok=False, error=str(exc)[:300])
            failures.append(f"{target}: {exc}")
            await ctx.log(f"{target} write failed: {exc}", level="warning")
            continue
        await record_result(ctx.session, suggestion_id, target, ok=True, error=None)
        await ctx.log(f"{target} set to {status}")

    if failures:
        raise RuntimeError("; ".join(failures)[:500])
    await ctx.log("status written everywhere", pct=100)
```

Add `list_write` to the handler import block in `backend/app/worker/main.py`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_status_sync.py tests/test_list_write.py -v`
Expected: PASS, 9 tests.

- [ ] **Step 7: Commit**

```bash
git add backend/app/discovery/status_sync.py backend/app/handlers/list_write.py backend/app/providers/anilist.py backend/app/providers/mal.py backend/app/sources/mangadex.py backend/app/worker/main.py backend/tests/test_status_sync.py backend/tests/test_list_write.py
git commit -m "feat(discovery): write the chosen status to every list"
```

---

### Task 10: Approve, dismiss and refresh

**Files:**
- Create: `backend/app/api/routes_discovery.py`
- Modify: `backend/app/api/main.py`
- Test: `backend/tests/test_discovery_api.py`

**Interfaces:**
- Consumes: `list_sync.create_series`, `list_sync.upsert_entry`, `queue_batches` is *not* used here; `repo.enqueue`; `source_for_url`.
- Produces:
  - `GET /api/suggestions` → `[{id, title, cover_url, total_chapters, year, publishing_status, rank_score, reason, sources, best_source, state}]`
  - `POST /api/suggestions/{id}/add` body `{status, download}` → `{ok, series_id, job_ids, needs_review}`
  - `POST /api/suggestions/{id}/dismiss` → `{ok: true}`
  - `POST /api/discovery/refresh` → `{ok: true, queued: int}`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_discovery_api.py
"""The Discovery screen's contract, against a real database."""

import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker

pytestmark = pytest.mark.asyncio

META = {
    "origin": {"provider": "anilist", "media_id": "21", "title": "Vinland Saga",
               "status": "completed", "progress_episode": 24, "total_episodes": 24},
    "relation": "SOURCE",
    "mangadex_uuid": "uuid-1",
    "sources": [{"site": "mangadex", "url": "https://mangadex.org/title/uuid-1",
                 "chapters": 210, "score": 0.98}],
    "best": {"site": "mangadex", "url": "https://mangadex.org/title/uuid-1", "score": 0.98},
}


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture
async def suggestion_id():
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                "truncate job, job_event, suggestion, list_entry, source_mapping, series "
                "restart identity cascade"
            )
        )
        new_id = (
            await session.execute(
                text(
                    """
                    insert into suggestion (provider, provider_media_id, alt_ids, title,
                                            total_chapters, publishing_status, rank_score, meta)
                    values ('anilist', '3000', '{"mal": "500"}'::jsonb, 'Vinland Saga', 210,
                            'RELEASING', 0.75, cast(:meta as jsonb))
                    returning id
                    """
                ),
                {"meta": json.dumps(META)},
            )
        ).scalar_one()
        await session.commit()
    yield new_id


async def test_the_screen_lists_new_suggestions_best_first(client, suggestion_id):
    body = (await client.get("/api/suggestions?state=new")).json()
    assert [s["id"] for s in body] == [suggestion_id]
    assert body[0]["rank_score"] == 0.75
    assert body[0]["reason"]["origin_title"] == "Vinland Saga"
    assert body[0]["best_source"]["site"] == "mangadex"


async def test_approving_creates_the_series_and_the_local_list_entries(client, suggestion_id):
    body = (
        await client.post(
            f"/api/suggestions/{suggestion_id}/add", json={"status": "reading", "download": False}
        )
    ).json()
    assert body["ok"] is True

    async with get_sessionmaker()() as session:
        series = (await session.execute(text("select id, canonical_title from series"))).one()
        entries = (
            await session.execute(
                text("select provider, provider_media_id, status from list_entry order by provider")
            )
        ).all()
    assert series.canonical_title == "Vinland Saga"
    assert [(e.provider, e.provider_media_id, e.status) for e in entries] == [
        ("anilist", "3000", "reading"),
        ("mal", "500", "reading"),
    ]


async def test_approving_queues_the_status_write(client, suggestion_id):
    await client.post(
        f"/api/suggestions/{suggestion_id}/add", json={"status": "reading", "download": False}
    )
    async with get_sessionmaker()() as session:
        types = [
            row[0]
            for row in (await session.execute(text("select type from job order by id"))).all()
        ]
    assert "list_write" in types


async def test_a_confident_candidate_maps_the_source_without_review(client, suggestion_id):
    await client.post(
        f"/api/suggestions/{suggestion_id}/add", json={"status": "reading", "download": True}
    )
    async with get_sessionmaker()() as session:
        mapping = (
            await session.execute(text("select source_site, source_url from source_mapping"))
        ).one()
        needs_review = (await session.execute(text("select needs_review from series"))).scalar_one()
    assert mapping.source_site == "mangadex"
    assert needs_review is False


async def test_not_downloading_now_queues_no_discovery(client, suggestion_id):
    await client.post(
        f"/api/suggestions/{suggestion_id}/add", json={"status": "reading", "download": False}
    )
    async with get_sessionmaker()() as session:
        types = [
            row[0] for row in (await session.execute(text("select type from job"))).all()
        ]
    assert "chapter_discover" not in types


async def test_downloading_now_queues_discovery(client, suggestion_id):
    await client.post(
        f"/api/suggestions/{suggestion_id}/add", json={"status": "reading", "download": True}
    )
    async with get_sessionmaker()() as session:
        types = [
            row[0] for row in (await session.execute(text("select type from job"))).all()
        ]
    assert "chapter_discover" in types


async def test_approving_marks_the_suggestion_added(client, suggestion_id):
    await client.post(
        f"/api/suggestions/{suggestion_id}/add", json={"status": "completed", "download": False}
    )
    async with get_sessionmaker()() as session:
        row = (await session.execute(text("select state, series_id from suggestion"))).one()
    assert row.state == "added"
    assert row.series_id is not None


async def test_a_dismissed_suggestion_leaves_the_new_list(client, suggestion_id):
    await client.post(f"/api/suggestions/{suggestion_id}/dismiss")
    assert (await client.get("/api/suggestions?state=new")).json() == []


async def test_refresh_queues_one_sync_per_provider(client, suggestion_id):
    body = (await client.post("/api/discovery/refresh")).json()
    assert body["queued"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_discovery_api.py -v`
Expected: FAIL — 404 on `/api/suggestions`.

- [ ] **Step 3: Write the routes**

```python
# backend/app/api/routes_discovery.py
"""Discovery screen: what to read next, and what happens when you say yes."""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.enums import JobType, ListStatus, Provider, SuggestionState
from app.handlers.list_sync import create_series, upsert_entry
from app.providers.base import ListEntryDTO
from app.queue import repo
from app.sources import source_for_url
from app.text_utils import normalize

router = APIRouter(prefix="/api", tags=["discovery"])

Session = Annotated[AsyncSession, Depends(db_session)]

# Below this, the best candidate is a guess, and a guess belongs on the review
# screen where the user can see what was rejected.
CONFIDENT_SCORE = 0.80

# Reading and planning to read are the statuses that mean "I want the files".
DOWNLOADING_STATUSES = {ListStatus.READING, ListStatus.PLAN_TO_READ}


class AddIn(BaseModel):
    status: ListStatus
    download: bool = False


@router.get("/suggestions")
async def list_suggestions(
    session: Session,
    state: Annotated[str, Query()] = "new",
    limit: Annotated[int, Query(le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, Any]]:
    result = await session.execute(
        text(
            """
            select id, provider, provider_media_id, alt_ids, title, cover_url, total_chapters,
                   year, publishing_status, state, rank_score, series_id, meta
              from suggestion
             where state = :state
             order by rank_score desc, title
             limit :limit offset :offset
            """
        ),
        {"state": state, "limit": limit, "offset": offset},
    )
    suggestions = []
    for row in result.all():
        meta = row.meta or {}
        origin = meta.get("origin") or {}
        suggestions.append(
            {
                "id": row.id,
                "title": row.title,
                "cover_url": row.cover_url,
                "total_chapters": row.total_chapters,
                "year": row.year,
                "publishing_status": row.publishing_status,
                "state": row.state,
                "rank_score": float(row.rank_score),
                "series_id": row.series_id,
                "reason": {
                    "origin_title": origin.get("title"),
                    "origin_status": origin.get("status"),
                    "total_episodes": origin.get("total_episodes"),
                    "relation": meta.get("relation"),
                },
                "sources": meta.get("sources", []),
                "best_source": meta.get("best"),
                "write_results": meta.get("write_results", []),
            }
        )
    return suggestions


async def _load(session: AsyncSession, suggestion_id: int) -> Any:
    result = await session.execute(
        text(
            """
            select id, provider, provider_media_id, alt_ids, title, cover_url, total_chapters,
                   state, meta
              from suggestion where id = :id
            """
        ),
        {"id": suggestion_id},
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="suggestion not found")
    return row


@router.post("/suggestions/{suggestion_id}/add")
async def add_suggestion(suggestion_id: int, body: AddIn, session: Session) -> dict[str, Any]:
    """Approving is what turns a suggestion into a series, a list entry and a status."""
    row = await _load(session, suggestion_id)
    if row.state == SuggestionState.ADDED:
        raise HTTPException(status_code=409, detail="suggestion already added")

    ids = {row.provider: row.provider_media_id, **(row.alt_ids or {})}
    titles = [row.title]
    aliases = [a for a in (normalize(t) for t in titles) if a]

    primary = ListEntryDTO(
        provider=Provider(row.provider),
        media_id=row.provider_media_id,
        status=body.status,
        title_english=row.title,
        total_chapters=row.total_chapters,
        cover_url=row.cover_url,
    )
    series_id = await create_series(session, primary, aliases)

    for provider, media_id in ids.items():
        await upsert_entry(
            session,
            ListEntryDTO(
                provider=Provider(provider),
                media_id=media_id,
                status=body.status,
                title_english=row.title,
                total_chapters=row.total_chapters,
                cover_url=row.cover_url,
            ),
            series_id,
        )

    job_ids: list[int | None] = [
        await repo.enqueue(
            session,
            JobType.LIST_WRITE,
            {"suggestion_id": suggestion_id, "status": str(body.status)},
            priority=0,
            dedupe_key=f"list_write:{suggestion_id}",
        )
    ]

    best = (row.meta or {}).get("best") or {}
    needs_review = True
    if best.get("url") and float(best.get("score") or 0) >= CONFIDENT_SCORE:
        try:
            site = source_for_url(best["url"]).site
        except ValueError:
            site = None
        if site:
            await session.execute(
                text(
                    """
                    insert into source_mapping (series_id, source_site, source_url, active,
                                                confirmed_at)
                    values (:series_id, :site, :url, true, now())
                    """
                ),
                {"series_id": series_id, "site": site, "url": best["url"]},
            )
            await session.execute(
                text("update series set needs_review = false where id = :id"),
                {"id": series_id},
            )
            needs_review = False

    if body.download and not needs_review:
        job_ids.append(
            await repo.enqueue(
                session,
                JobType.CHAPTER_DISCOVER,
                {"series_id": series_id},
                priority=0,
                series_id=series_id,
                dedupe_key=f"chapter_discover:{series_id}",
            )
        )
        await session.execute(
            text("update series set auto_download = true where id = :id"), {"id": series_id}
        )

    await session.execute(
        text(
            """
            update suggestion
               set state = 'added',
                   series_id = :series_id,
                   meta = coalesce(meta, '{}'::jsonb) || cast(:extra as jsonb),
                   updated_at = now()
             where id = :id
            """
        ),
        {
            "id": suggestion_id,
            "series_id": series_id,
            "extra": json.dumps({"chosen_status": str(body.status), "download": body.download}),
        },
    )
    await session.commit()
    return {
        "ok": True,
        "series_id": series_id,
        "job_ids": [j for j in job_ids if j],
        "needs_review": needs_review,
    }


@router.post("/suggestions/{suggestion_id}/dismiss")
async def dismiss_suggestion(suggestion_id: int, session: Session) -> dict[str, bool]:
    """Dismissal is permanent: the row stays so the next build cannot resurrect it."""
    await _load(session, suggestion_id)
    await session.execute(
        text("update suggestion set state = 'dismissed', updated_at = now() where id = :id"),
        {"id": suggestion_id},
    )
    await session.commit()
    return {"ok": True}


@router.post("/discovery/refresh")
async def refresh(session: Session) -> dict[str, Any]:
    queued = 0
    for provider in Provider:
        job_id = await repo.enqueue(
            session,
            JobType.ANIME_LIST_SYNC,
            {"provider": str(provider)},
            priority=0,
            dedupe_key=f"anime_list_sync:{provider}",
        )
        queued += 1 if job_id else 0
    await session.commit()
    return {"ok": True, "queued": queued}
```

Register it in `backend/app/api/main.py`: import `routes_discovery` and `app.include_router(routes_discovery.router)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_discovery_api.py -v`
Expected: PASS, 9 tests.

- [ ] **Step 5: Run the whole backend suite**

Run: `cd backend && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check app tests`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes_discovery.py backend/app/api/main.py backend/tests/test_discovery_api.py
git commit -m "feat(discovery): approve, dismiss and refresh suggestions"
```

---

### Task 11: A completed manga is marked read in Komga

**Files:**
- Modify: `backend/app/handlers/komga_scan.py`
- Test: `backend/tests/test_komga_completed.py`

**Interfaces:**
- Consumes: `suggestion.meta.chosen_status` written in Task 10; `KomgaClient.books_of_series`, `KomgaClient.set_read_progress`.
- Produces: `app.handlers.komga_scan.completed_series(session, series_id) -> bool`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_komga_completed.py
"""A manga added as completed should not arrive in Komga as unread."""

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.handlers.komga_scan import completed_series

pytestmark = pytest.mark.asyncio


async def _series_with_status(status: str | None) -> int:
    async with get_sessionmaker()() as session:
        await session.execute(
            text("truncate suggestion, series restart identity cascade")
        )
        series_id = (
            await session.execute(
                text(
                    """
                    insert into series (canonical_title, slug, needs_review, meta, created_at)
                    values ('V', 'v-komga', false, '{}'::jsonb, now()) returning id
                    """
                )
            )
        ).scalar_one()
        if status is not None:
            await session.execute(
                text(
                    """
                    insert into suggestion (provider, provider_media_id, title, series_id,
                                            state, alt_ids, meta)
                    values ('anilist', '3000', 'V', :sid, 'added', '{}'::jsonb,
                            jsonb_build_object('chosen_status', :status))
                    """
                ),
                {"sid": series_id, "status": status},
            )
        await session.commit()
    return series_id


async def test_a_series_added_as_completed_is_marked_read():
    series_id = await _series_with_status("completed")
    async with get_sessionmaker()() as session:
        assert await completed_series(session, series_id) is True


async def test_a_series_added_as_reading_is_left_alone():
    series_id = await _series_with_status("reading")
    async with get_sessionmaker()() as session:
        assert await completed_series(session, series_id) is False


async def test_a_series_that_never_came_from_discovery_is_left_alone():
    series_id = await _series_with_status(None)
    async with get_sessionmaker()() as session:
        assert await completed_series(session, series_id) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_komga_completed.py -v`
Expected: FAIL — `ImportError: cannot import name 'completed_series'`.

- [ ] **Step 3: Implement**

In `backend/app/handlers/komga_scan.py`:

```python
async def completed_series(session: AsyncSession, series_id: int) -> bool:
    """True when the user added this series already finished, so Komga should agree."""
    result = await session.execute(
        text(
            """
            select 1 from suggestion
             where series_id = :series_id
               and state = 'added'
               and meta ->> 'chosen_status' = 'completed'
             limit 1
            """
        ),
        {"series_id": series_id},
    )
    return result.first() is not None
```

At the end of the `KOMGA_SCAN` handler, after the books have been matched to chapters and `komga_book_id` stored, add:

```python
    if await completed_series(ctx.session, series_id):
        for book in books:
            await client.set_read_progress(book.id, page=1, completed=True)
        await ctx.log(f"marked {len(books)} books read: added as completed")
```

Use the handler's existing client and `books` variable names; if they differ, adapt rather than introducing new fetches.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_komga_completed.py tests/test_progress_push.py -v`
Expected: PASS — and `progress_push` still untouched, since only status, never progress, flows outward from discovery.

- [ ] **Step 5: Commit**

```bash
git add backend/app/handlers/komga_scan.py backend/tests/test_komga_completed.py
git commit -m "feat(komga): mark a series added as completed already read"
```

---

### Task 12: The Discovery screen

**Files:**
- Create: `frontend/src/pages/Discovery.tsx`
- Modify: `frontend/src/api.ts`, `frontend/src/App.tsx`, `frontend/src/pages/Settings.tsx`, `frontend/src/styles.css`
- Modify: `backend/app/api/routes_settings.py`

**Interfaces:**
- Consumes: the endpoints from Task 10; `useJobEvents` from `frontend/src/useEvents.ts`.
- Produces: `api.suggestions`, `api.addSuggestion`, `api.dismissSuggestion`, `api.refreshDiscovery`; the `/discovery` route.

- [ ] **Step 1: Expose the new cron and the comick health in settings**

In `backend/app/api/routes_settings.py`: add `settings_store.CRON_ANIME_LIST_SYNC` to `EDITABLE`, and add comick to the `sources` block of the response:

```python
    from app.sources.comick_client import ComickClient

    comick_up = await ComickClient().health()
```

```python
            "comick": {"authenticated": comick_up, "username": None},
```

- [ ] **Step 2: Add the client calls**

In `frontend/src/api.ts`:

```ts
export interface SuggestionSource {
  site: string
  url: string
  chapters: number | null
  score: number
}

export interface Suggestion {
  id: number
  title: string
  cover_url: string | null
  total_chapters: number | null
  year: number | null
  publishing_status: string | null
  state: 'new' | 'dismissed' | 'added'
  rank_score: number
  series_id: number | null
  reason: {
    origin_title: string | null
    origin_status: string | null
    total_episodes: number | null
    relation: string | null
  }
  sources: SuggestionSource[]
  best_source: { site: string; url: string; score: number } | null
  write_results: { target: string; ok: boolean; error: string | null }[]
}

export type ListStatusValue = 'reading' | 'plan_to_read' | 'completed' | 'on_hold' | 'dropped'
```

```ts
  suggestions: (state = 'new') => request<Suggestion[]>(`/api/suggestions?state=${state}`),
  addSuggestion: (id: number, status: ListStatusValue, download: boolean) =>
    request<{ ok: boolean; series_id: number; needs_review: boolean }>(
      `/api/suggestions/${id}/add`,
      { method: 'POST', body: JSON.stringify({ status, download }) },
    ),
  dismissSuggestion: (id: number) =>
    request<{ ok: boolean }>(`/api/suggestions/${id}/dismiss`, { method: 'POST' }),
  refreshDiscovery: () =>
    request<{ ok: boolean; queued: number }>('/api/discovery/refresh', { method: 'POST' }),
```

- [ ] **Step 3: Write the screen**

```tsx
// frontend/src/pages/Discovery.tsx
import { useEffect, useState } from 'react'

import { api, ListStatusValue, Suggestion } from '../api'
import { useJobEvents } from '../useEvents'

const STATUSES: { value: ListStatusValue; label: string }[] = [
  { value: 'reading', label: 'Lendo' },
  { value: 'plan_to_read', label: 'Planejo ler' },
  { value: 'completed', label: 'Completo' },
  { value: 'on_hold', label: 'Em espera' },
  { value: 'dropped', label: 'Dropado' },
]

const DOWNLOADS_BY_DEFAULT: ListStatusValue[] = ['reading', 'plan_to_read']

function reasonOf(suggestion: Suggestion): string {
  const { origin_title, origin_status } = suggestion.reason
  if (!origin_title) return 'Relacionado a um anime da sua lista'
  const watched = origin_status === 'completed' ? 'anime completo' : 'anime em andamento'
  const chapters = suggestion.total_chapters
  const beyond = chapters ? ` — mangá vai até o capítulo ${chapters}` : ''
  return `de ${origin_title}, ${watched}${beyond}`
}

export function Discovery({ onChanged }: { onChanged: () => void }) {
  const [items, setItems] = useState<Suggestion[]>([])
  const [choice, setChoice] = useState<Record<number, { status: ListStatusValue; download: boolean }>>({})
  const [busy, setBusy] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    api.suggestions('new').then(setItems).catch((e) => setError(String(e)))
  }

  useEffect(load, [])
  useJobEvents(load)

  const settingFor = (item: Suggestion) =>
    choice[item.id] ?? { status: 'reading' as ListStatusValue, download: true }

  const setStatus = (item: Suggestion, status: ListStatusValue) =>
    setChoice((current) => ({
      ...current,
      [item.id]: { status, download: DOWNLOADS_BY_DEFAULT.includes(status) },
    }))

  const setDownload = (item: Suggestion, download: boolean) =>
    setChoice((current) => ({ ...current, [item.id]: { ...settingFor(item), download } }))

  const add = async (item: Suggestion) => {
    const { status, download } = settingFor(item)
    setBusy(item.id)
    try {
      await api.addSuggestion(item.id, status, download)
      setItems((current) => current.filter((s) => s.id !== item.id))
      onChanged()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(null)
    }
  }

  const dismiss = async (item: Suggestion) => {
    setBusy(item.id)
    try {
      await api.dismissSuggestion(item.id)
      setItems((current) => current.filter((s) => s.id !== item.id))
      onChanged()
    } finally {
      setBusy(null)
    }
  }

  return (
    <section>
      <header className="page-head">
        <h1>Discovery</h1>
        <button onClick={() => api.refreshDiscovery().then(load)}>Procurar agora</button>
      </header>
      {error && <p className="error">{error}</p>}
      {items.length === 0 && <p className="empty">Nada novo. A lista de anime já virou mangá.</p>}
      <div className="grid">
        {items.map((item) => (
          <article className="card" key={item.id}>
            {item.cover_url && <img src={item.cover_url} alt="" loading="lazy" />}
            <h2>{item.title}</h2>
            <p className="reason">{reasonOf(item)}</p>
            <p className="sources">
              {item.sources.map((source) => (
                <span
                  key={source.site}
                  className={source.site === item.best_source?.site ? 'chip chip-best' : 'chip'}
                >
                  {source.site}
                </span>
              ))}
            </p>
            <label>
              Status
              <select
                value={settingFor(item).status}
                onChange={(event) => setStatus(item, event.target.value as ListStatusValue)}
              >
                {STATUSES.map((status) => (
                  <option key={status.value} value={status.value}>
                    {status.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="toggle">
              <input
                type="checkbox"
                checked={settingFor(item).download}
                onChange={(event) => setDownload(item, event.target.checked)}
              />
              Baixar agora
            </label>
            <div className="actions">
              <button disabled={busy === item.id} onClick={() => add(item)}>
                Adicionar
              </button>
              <button className="ghost" disabled={busy === item.id} onClick={() => dismiss(item)}>
                Dispensar
              </button>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
```

- [ ] **Step 4: Wire the route and the badge**

In `frontend/src/App.tsx`: import `Discovery`, count suggestions in `refreshBadges`

```tsx
    api
      .suggestions('new')
      .then((items) => setSuggestionCount(items.length))
      .catch(() => undefined)
```

add the nav link next to Review

```tsx
          <NavLink to="/discovery">
            Discovery {suggestionCount > 0 && <b className="badge">{suggestionCount}</b>}
          </NavLink>
```

and the route

```tsx
          <Route path="/discovery" element={<Discovery onChanged={refreshBadges} />} />
```

In `frontend/src/pages/Settings.tsx`, add `cron_anime_list_sync` to the rendered settings keys, following whatever list or map that file already uses, with the label "Sync da lista de anime".

In `frontend/src/styles.css`, add the few classes the screen introduces (`.reason`, `.sources`, `.chip`, `.chip-best`, `.toggle`, `.page-head`), matching the existing visual language of `.card` and `.grid`.

- [ ] **Step 5: Build the frontend**

Run: `cd frontend && npm run build`
Expected: build succeeds with no TypeScript errors.

- [ ] **Step 6: Exercise it end to end**

Run: `docker compose up -d --build`, open <http://localhost:8080/discovery>, then:
- press "Procurar agora" and watch the Downloads screen show `anime_list_sync` and then `suggest_build` finishing;
- confirm cards appear with a reason and source chips;
- approve one as "Planejo ler" with "Baixar agora" off, then check the manga now carries that status on MyAnimeList, AniList and MangaDex, that Library shows the series, and that no chapter was queued;
- approve one as "Lendo" with "Baixar agora" on and confirm chapters download and reach Komga;
- dismiss one, press "Procurar agora" again, and confirm it does not come back.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Discovery.tsx frontend/src/api.ts frontend/src/App.tsx frontend/src/pages/Settings.tsx frontend/src/styles.css backend/app/api/routes_settings.py
git commit -m "feat(ui): add the discovery screen"
```

---

### Task 13: Document it

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: everything above.
- Produces: no code.

- [ ] **Step 1: Extend the README**

Add a "Discovery" section after "Como funciona" explaining, in the README's existing voice and language: the anime lists are read on their own schedule; a manga an anime adapts becomes a suggestion unless it is already on a list; approving it writes the chosen status to MyAnimeList, AniList and MangaDex and optionally starts the download; dismissal is permanent. Extend the diagram with the anime list feeding Discovery. Mention `COMICK_API_URL` and the bundled `comick` service in the environment table, and note that comick supplies search and chapter listings only — downloads stay with the binary.

- [ ] **Step 2: Verify the whole suite one last time**

Run: `cd backend && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check app tests && cd ../frontend && npm run build`
Expected: all green.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: describe the discovery flow"
```

---

## Self-Review

**Spec coverage:** `anime_entry`/`suggestion` and enums → Task 1. AniList-first relations with MAL fallback → Tasks 2-4. Identity collapse, exclusion rules, ranking → Tasks 5-6. Comick service, client, registered sources, degradation → Task 7. Source summary and the MangaDex uuid kept regardless of download source → Task 8. Status map for the four destinations, `LIST_WRITE`, partial failure and retry → Task 9. Approval flow, per-item download toggle, confident mapping skipping Review, permanent dismissal, refresh → Task 10. Komga marking a completed series read, and the status/progress boundary → Task 11. Discovery screen, badge, settings → Task 12. Docs → Task 13. Acceptance criteria 1-8 all map onto a test in Tasks 4, 6, 9, 10 and 11.

**Naming:** `upsert_anime`, `needs_mal_relations`, `seeds_from`, `collapse`, `rank_score`, `beyond_signal`, `already_known`, `upsert_suggestion`, `source_summary`, `targets_for`, `pending_targets`, `record_result`, `completed_series` are each defined once and referenced under that same name everywhere else. `MangaMeta` is defined in Task 6 before Tasks 6 and 8 use it; `Candidate` and `ChapterRef` come from the existing `app.sources.base`.
