# Source Selection v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reach the five scan sites this library actually downloads from, search them all when a series needs matching, and let the user turn sites on and off from Settings.

**Architecture:** Two ported templates (`mangathemesia`, `iken`) and two hand-written sources (MangaGeko, Asura Scans) join the existing `Source` contract. A template is a Python class; a site on that template is an *instance* configured from its `site_catalogue.overrides` row, not a subclass. `match_search` stops looping sources one at a time and fans out with bounded concurrency, a per-source timeout and partial results. A new `/api/sources` serves and toggles the catalogue, and a panel under the existing Settings screen drives it.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async, asyncpg, Alembic, httpx, selectolax or BeautifulSoup (whichever the repo already carries — check `backend/pyproject.toml` before adding one), pytest, React 18, TypeScript, Vite, Tailwind CSS 3.

**Spec:** `docs/superpowers/specs/2026-09-15-tachiyomi-extension-port-design.md`

## Global Constraints

- Everything in the repository is English: code, comments, commit messages, issues, pull requests, documentation and the interface.
- No commit may mention or credit an assistant. No `Co-Authored-By` naming one, no generated-with footer, no trailer of any kind. Enable the hook once: `git config core.hooksPath .githooks`.
- Micro commits: one focused change each, self-contained and buildable. Imperative scoped subject (`feat(sources):`, `fix(api):`). The body says *why*.
- `sources/`, `downloader/` and `komga/` are pure at their edges: they take arguments and return values and **never touch the database**. Only `handlers/` writes.
- Tests run against a real throwaway Postgres. This worktree uses **port 5438**: `docker run -d --name manga-pg-source-v1 -e POSTGRES_USER=manga -e POSTGRES_PASSWORD=manga -e POSTGRES_DB=manga -p 5438:5432 postgres:17-alpine`, then `POSTGRES_HOST=localhost POSTGRES_PORT=5438 .venv/bin/python -m pytest tests -q`. Never reuse 5433, 5434 or 5435 — a schema migrated by another branch makes the suite lie about this one.
- `alembic` is not on PATH. Invoke it as `python -m alembic`, including from subprocesses in tests.
- `.venv/bin/python -m ruff check app/ tests/` must be clean.
- asyncpg cannot infer the type of a null parameter: `:x is null` must be `cast(:x as text) is null`.
- A value that looks numeric may arrive as a string, or as an empty one. An empty string reaching an integer column fails at bind time, far from the parser that let it through.
- `frontend/tailwind.config.ts` is the only place a colour, size, radius or spacing value lives. No hex, px or rem literal in a component.
- **A Tailwind class is only real if the built CSS contains it.** After building, `grep` `frontend/dist/` for every class introduced. Escaped selectors need literal matching — a regex misses the backslash. Three classes on an earlier branch typechecked, built clean and generated nothing: a name built by string interpolation, `font-label-md` (the scale exists only under `fontSize`, so `text-label-md` carries size *and* weight), and `bg-secondary/12` (the opacity modifier takes scale steps; 12 needs `/[0.12]`).
- Feature folders never import from each other. Anything two screens need lives in `ui/` or `lib/`.
- No screen renders a number the API cannot serve.
- A screen's own data goes through `lib/useAsyncData.ts`, so loading, empty, failed, and failed-refresh-over-loaded-data are four distinguishable states.
- Comments explain the reason a line exists, never what it does.

## Porting rule — read this before Task 2

The upstream extensions are Kotlin, licensed Apache 2.0, at
[yuzono/tachiyomi-extensions](https://github.com/yuzono/tachiyomi-extensions). **This plan does not
reproduce their source, and neither should you.** Port them: read the upstream file, understand what
it asks the site for and what it pulls out of the answer, then write Python that does the same thing
in this codebase's idiom. Do not paste Kotlin and translate it line by line — you will carry over
structure that does not fit `Source`, and you will produce a file nobody can review against the site
it talks to.

Every task below therefore specifies, completely: the class shape, the attribute names, the method
signatures, the fixture files and the assertions. What it does not hand you is the selector strings —
those come from the upstream file and from the fixture you record, and inventing them here would be
guessing at markup neither of us has looked at.

Record each fixture from the live site, once, and check it in:

```bash
curl -s -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36' \
  'https://en-thunderscans.com/?s=rebirth' > backend/tests/fixtures/sources/thunderscans_search.html
```

Trim a fixture to the smallest page that still exercises the parser. A 900 KB page in the repository
is a fixture nobody will ever re-record.

## File Structure

**Created**

| Path | Responsibility |
|---|---|
| `backend/app/sources/templates/__init__.py` | Package marker, exports `TemplateSource`. |
| `backend/app/sources/templates/base.py` | `TemplateSource`: holds a `SiteClient`, declares the overridable attributes, implements nothing site-specific. |
| `backend/app/sources/templates/mangathemesia.py` | The `mangathemesia` template. |
| `backend/app/sources/templates/iken.py` | The `iken` template. |
| `backend/app/sources/mangageko.py` | MangaGeko, standalone. |
| `backend/app/sources/asurascans.py` | Asura Scans, standalone. |
| `backend/alembic/versions/0013_seed_v1_sites.py` | Catalogue and preference rows for the five sites. |
| `backend/app/api/routes_sources.py` | `GET /api/sources`, `PUT /api/sources/{key}`. |
| `frontend/src/features/settings/useSources.ts` | Fetch, page, filter and toggle. |
| `frontend/src/features/settings/SourcesPanel.tsx` | The panel: search, filters, list, paging. |
| `frontend/src/features/settings/SourceRow.tsx` | One catalogue row. |

**Modified**

| Path | Change |
|---|---|
| `backend/app/sources/registry.py` | Instantiate template sources from `overrides`, not only `NATIVE_SOURCES`. |
| `backend/app/handlers/match_search.py` | Bounded concurrent fan-out, per-source timeout, partial results. |
| `backend/app/settings_store.py` | `source_search_concurrency`, `source_search_timeout`. |
| `backend/app/api/routes_settings.py` | Add both keys to `EDITABLE`. |
| `backend/app/api/main.py` | Register `routes_sources`. |
| `frontend/src/lib/api.ts` | `sources()`, `setSourceEnabled()`, their types. |
| `frontend/src/features/settings/SettingsPage.tsx` | Mount `SourcesPanel`. |

---

### Task 1: `TemplateSource`, and a registry that can build one

**Files:**
- Create: `backend/app/sources/templates/__init__.py`
- Create: `backend/app/sources/templates/base.py`
- Modify: `backend/app/sources/registry.py`
- Test: `backend/tests/test_source_registry.py`

**Interfaces:**
- Consumes: `app.sources.base.Source`, `Candidate`, `ChapterRef`, `PageRef`; `app.sources.net.CatalogueRow`, `SiteClient`, `get_client`.
- Produces: `TemplateSource(row, name=..., lang=..., overrides=...)` with class attributes `template: ClassVar[str]` and `overridable: ClassVar[frozenset[str]]`; `app.sources.registry.TEMPLATE_CLASSES: dict[str, type[TemplateSource]]`, which Tasks 2 and 3 add entries to.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_source_registry.py`:

```python
import pytest
from sqlalchemy import text

from app.sources import registry
from app.sources.base import Candidate, ChapterRef, PageRef, get_source
from app.sources.net import CatalogueRow
from app.sources.templates import TemplateSource


class FakeTemplate(TemplateSource):
    template = "faketemplate"
    overridable = frozenset({"search_path"})
    search_path = "/default"

    async def search(self, titles, *, limit=8) -> list[Candidate]:
        return []

    async def list_chapters(self, url, *, language="en") -> list[ChapterRef]:
        return []

    async def list_pages(self, chapter_url, *, language="en") -> list[PageRef]:
        return []


async def _row(session, key, template, overrides="{}"):
    await session.execute(
        text(
            """
            insert into site_catalogue
                (key, name, template, base_url, lang, nsfw, overrides, version, hand_ported)
            values (:key, :key, :template, 'https://' || :key || '.test', 'en', false,
                    cast(:overrides as jsonb), '1', true)
            on conflict (key) do nothing
            """
        ),
        {"key": key, "template": template, "overrides": overrides},
    )
    await session.execute(
        text("insert into source_pref (key, enabled) values (:key, true) on conflict do nothing"),
        {"key": key},
    )


async def test_a_template_row_becomes_a_source_instance(session, monkeypatch):
    monkeypatch.setitem(registry.TEMPLATE_CLASSES, "faketemplate", FakeTemplate)
    await _row(session, "sitea", "faketemplate", '{"search_path": "/find"}')

    await registry.reload(session)

    source = get_source("sitea")
    assert isinstance(source, FakeTemplate)
    # The override travels from the catalogue row onto the instance: that is
    # what makes a leaf configuration rather than code.
    assert source.search_path == "/find"
    assert source.base_url == "https://sitea.test"


async def test_an_unknown_override_skips_the_site_instead_of_failing_the_boot(
    session, monkeypatch, caplog
):
    monkeypatch.setitem(registry.TEMPLATE_CLASSES, "faketemplate", FakeTemplate)
    await _row(session, "siteb", "faketemplate", '{"no_such_attribute": 1}')

    await registry.reload(session)

    # One bad generated row must not take every other site down with it.
    with pytest.raises(ValueError):
        get_source("siteb")
    assert "no_such_attribute" in caplog.text
```

- [ ] **Step 2: Run the test and watch it fail**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5438 .venv/bin/python -m pytest tests/test_source_registry.py -q
```

Expected: FAIL, `ModuleNotFoundError: No module named 'app.sources.templates'`.

- [ ] **Step 3: Write `backend/app/sources/templates/base.py`**

```python
"""A ported template, and the rule that a site on it is configuration.

Upstream, a site is a Kotlin class that subclasses its template and overrides a
handful of members - and across the leaves that matter here, almost every
override is a constant. Reproducing that as one Python subclass per site would
put 117 near-empty modules in this repository and make enabling a site a code
change again, which is the thing `registry.reload` exists to undo. So a template
is a class and a site is an *instance* of it, configured from its
`site_catalogue.overrides` row.
"""

from typing import Any, ClassVar

from app.sources.base import Source
from app.sources.net import CatalogueRow, SiteClient, get_client


class TemplateSource(Source):
    #: Matches `site_catalogue.template`; `registry.TEMPLATE_CLASSES` keys on it.
    template: ClassVar[str] = ""

    #: Attribute names a catalogue row may set through `overrides`. An allow-list
    #: rather than free assignment: a generated row naming an attribute this
    #: template does not have is a generator bug, and silently absorbing it would
    #: leave the site half-configured and parsing against defaults nobody chose.
    overridable: ClassVar[frozenset[str]] = frozenset()

    def __init__(
        self,
        row: CatalogueRow,
        *,
        name: str,
        lang: str = "en",
        overrides: dict[str, Any] | None = None,
        client: SiteClient | None = None,
    ) -> None:
        self.site = row.key
        # The catalogue row's base_url is the site's host; `domains` stays the
        # extra aliases a hand-written class carries, and a template leaf has none.
        self.domains: tuple[str, ...] = ()
        self.name = name
        self.lang = lang
        self.base_url = row.base_url.rstrip("/")
        # Injectable so a test drives the template against a recorded fixture
        # without a live site or a live rate limit.
        self.client = client or get_client(row)
        for attribute, value in (overrides or {}).items():
            if attribute not in self.overridable:
                raise ValueError(
                    f"{self.template}: {attribute!r} is not an overridable attribute"
                )
            setattr(self, attribute, value)

    def absolute(self, url: str) -> str:
        """Site-relative hrefs are the norm in this markup; a stored candidate URL
        that is not absolute cannot be pasted back into Review later."""
        if url.startswith(("http://", "https://")):
            return url
        return f"{self.base_url}/{url.lstrip('/')}"
```

And `backend/app/sources/templates/__init__.py`:

```python
from app.sources.templates.base import TemplateSource

__all__ = ["TemplateSource"]
```

- [ ] **Step 4: Teach the registry to build them**

In `backend/app/sources/registry.py`, add the import and the table:

```python
from app.sources.net import CatalogueRow
from app.sources.templates import TemplateSource

# Filled by the template ports. A template with no entry here is a row the
# catalogue knows about and this deployment cannot yet run - `reload` says so
# and skips it, which is the same answer it already gives an unknown template.
TEMPLATE_CLASSES: dict[str, type[TemplateSource]] = {}
```

Replace the `select` in `reload` with one that carries everything a template
instance needs:

```python
    rows = (
        await session.execute(
            text(
                """
                select c.key, c.name, c.template, c.base_url, c.lang,
                       c.overrides, c.rate_limit, p.rate_limit_override
                  from site_catalogue c
                  join source_pref p on p.key = c.key
                 where p.enabled
                """
            )
        )
    ).mappings().all()
```

and replace the body of the loop's `else` branch — the `template != "native"`
skip — with construction:

```python
    for row in rows:
        if row["template"] == "native":
            source = NATIVE_SOURCES.get(row["key"])
            if source is None:
                logger.warning(
                    "site %s: template=native but no class is registered for that key, skipping",
                    row["key"],
                )
                continue
        else:
            template_class = TEMPLATE_CLASSES.get(row["template"])
            if template_class is None:
                logger.warning(
                    "site %s: template %r has no implementation yet, skipping",
                    row["key"],
                    row["template"],
                )
                continue
            try:
                source = template_class(
                    CatalogueRow(
                        key=row["key"],
                        base_url=row["base_url"],
                        rate_limit=row["rate_limit"],
                        rate_limit_override=row["rate_limit_override"],
                    ),
                    name=row["name"],
                    lang=row["lang"],
                    overrides=row["overrides"] or {},
                )
            except ValueError as exc:
                logger.warning("site %s: %s, skipping", row["key"], exc)
                continue
        entries[source.site] = RegisteredSource(source=source, base_url=row["base_url"])
```

- [ ] **Step 5: Run the tests and ruff**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5438 .venv/bin/python -m pytest tests/test_source_registry.py -q
.venv/bin/python -m ruff check app/ tests/
```

Expected: PASS, clean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/sources/templates backend/app/sources/registry.py backend/tests/test_source_registry.py
git commit -m "feat(sources): build template sources from their catalogue row

A site on a shared template is now an instance configured from
site_catalogue.overrides rather than a class of its own. One subclass per
site would put a hundred near-empty modules in the tree and make enabling a
site a code change again, which is what the registry exists to undo.

An override naming an attribute the template does not have skips that site
with a log line instead of failing the boot: it is a generator bug, and one
bad row must not take the other sites down."
```

---

### Task 2: the `mangathemesia` template, and the five catalogue rows

**Files:**
- Create: `backend/app/sources/templates/mangathemesia.py`
- Create: `backend/alembic/versions/0013_seed_v1_sites.py`
- Create: `backend/tests/fixtures/sources/thunderscans_search.html`
- Create: `backend/tests/fixtures/sources/thunderscans_chapters.html`
- Create: `backend/tests/fixtures/sources/thunderscans_pages.html`
- Create: `backend/tests/test_template_mangathemesia.py`
- Modify: `backend/app/sources/registry.py` (add the `TEMPLATE_CLASSES` entry)

**Interfaces:**
- Consumes: `TemplateSource` from Task 1.
- Produces: `MangaThemesiaSource`, registered as `TEMPLATE_CLASSES["mangathemesia"]`. Catalogue keys `thunderscans`, `vortexscans`, `orionscans`, `mangageko`, `asurascans` exist from this task onward; Tasks 3–5 supply the classes for the last four.

**Read first:** `lib-multisrc/mangathemesia/` upstream. It is the largest of the two templates here,
about 34 KB of Kotlin across the template and its helpers. Note as you read: how search builds its
query, how the chapter list is reached, and where the page list lives. The design doc records that
this template reads its pages out of a JSON blob embedded in a script tag rather than from an image
list in the markup — confirm that against the file, because it decides the shape of `list_pages`.

- [ ] **Step 1: Record the three fixtures**

```bash
cd backend
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
mkdir -p tests/fixtures/sources
curl -s -H "User-Agent: $UA" 'https://en-thunderscans.com/?s=rebirth' > tests/fixtures/sources/thunderscans_search.html
curl -s -H "User-Agent: $UA" 'https://en-thunderscans.com/comics/rebirth-monarch-of-the-dead/' > tests/fixtures/sources/thunderscans_chapters.html
```

For the third, open the chapter list you just recorded, pick the first chapter URL out of it, and
record that page as `thunderscans_pages.html`. Trim each file to the smallest page that still
exercises the parser.

Check all three in. If the site is unreachable or has changed shape so far that the upstream
template no longer matches it, **stop and report that** rather than writing a parser against a page
you could not read — a template ported against guessed markup fails silently, at download time,
weeks later.

- [ ] **Step 2: Write the failing test**

`backend/tests/test_template_mangathemesia.py`:

```python
"""Golden tests for the mangathemesia template, driven by recorded pages.

sources/ is pure and fixture-driven (CLAUDE.md, "Module boundaries"): no
network in this suite, so a site changing its markup breaks a re-recorded
fixture rather than a Tuesday's downloads.
"""

from decimal import Decimal
from pathlib import Path

from app.sources.net import CatalogueRow
from app.sources.templates.mangathemesia import MangaThemesiaSource

FIXTURES = Path(__file__).parent / "fixtures" / "sources"

ROW = CatalogueRow(key="thunderscans", base_url="https://en-thunderscans.com")


def _source() -> MangaThemesiaSource:
    # client=None is never reached: every test here calls a pure parser
    # directly rather than anything that makes a request.
    return MangaThemesiaSource(ROW, name="Thunder Scans", client=object())


def test_search_parses_candidates_from_the_recorded_page():
    html = (FIXTURES / "thunderscans_search.html").read_text()

    found = _source().parse_search(html, ["Rebirth Monarch of the Dead"])

    assert found, "the recorded search page yielded no candidates"
    for candidate in found:
        assert candidate.source_site == "thunderscans"
        assert candidate.source_url.startswith("https://"), candidate.source_url
        assert candidate.title
    # Best match first, the same contract every other source keeps.
    assert found == sorted(found, key=lambda c: c.score, reverse=True)
    # Golden: replace with the title the fixture you recorded actually carries.
    assert found[0].title == "Rebirth Monarch of the Dead"


def test_chapters_parse_in_descending_order_with_usable_numbers():
    html = (FIXTURES / "thunderscans_chapters.html").read_text()

    chapters = _source().parse_chapters(html)

    assert chapters
    numbers = [c.number for c in chapters]
    assert numbers == sorted(numbers, reverse=True), "chapter order is the site's, newest first"
    assert all(isinstance(n, Decimal) for n in numbers)
    assert all(c.url.startswith("https://") for c in chapters)
    # A decimal chapter is the case that breaks a naive int() parse. If the
    # fixture has none, record one that does rather than deleting this.
    assert any(n % 1 for n in numbers)


def test_pages_parse_in_reading_order_and_carry_a_referer():
    html = (FIXTURES / "thunderscans_pages.html").read_text()

    pages = _source().parse_pages(html, "https://en-thunderscans.com/rebirth-chapter-1/")

    assert pages
    assert all(p.url.startswith("https://") for p in pages)
    # Many of these sites answer 403 to a hotlinked image; the referer is why
    # PageRef carries headers at all (sources/base.py).
    assert all(p.headers.get("Referer") for p in pages)
```

- [ ] **Step 3: Run it and watch it fail**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5438 .venv/bin/python -m pytest tests/test_template_mangathemesia.py -q
```

Expected: FAIL, `ModuleNotFoundError: No module named 'app.sources.templates.mangathemesia'`.

- [ ] **Step 4: Write the template**

This is the skeleton and the contract. The selector strings and the search query shape come from the
upstream file and the fixture you recorded — fill them in as you go, and give every non-obvious one a
comment naming what it matches.

```python
"""The mangathemesia template.

Ported from lib-multisrc/mangathemesia upstream, not transcribed: the shape
below is this codebase's Source contract, and what was read from the Kotlin is
which request each operation makes and which parts of the answer matter.
"""

from decimal import Decimal, InvalidOperation
from typing import ClassVar

from app.sources.base import Candidate, ChapterRef, PageRef
from app.sources.templates import TemplateSource
from app.text_utils import best_similarity


class MangaThemesiaSource(TemplateSource):
    template: ClassVar[str] = "mangathemesia"

    #: Every attribute a generated leaf is allowed to set. Add a name here only
    #: once this class actually reads it - an allow-list that promises more than
    #: the parser honours is worse than one that refuses.
    overridable: ClassVar[frozenset[str]] = frozenset(
        {"manga_sub_string", "search_path", "date_format"}
    )

    #: The path segment a series lives under. Upstream calls this mangaSubString
    #: and 67 leaves override it, which is why it is the first one here.
    manga_sub_string: str = "manga"
    search_path: str = "/?s={query}"
    date_format: str = "MMMM d, yyyy"

    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]:
        query = titles[0] if titles else ""
        response = await self.client.get(self.search_path.format(query=query))
        response.raise_for_status()
        return self.parse_search(response.text, titles)[:limit]

    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        response = await self.client.get(url)
        response.raise_for_status()
        return self.parse_chapters(response.text)

    async def list_pages(self, chapter_url: str, *, language: str = "en") -> list[PageRef]:
        response = await self.client.get(chapter_url)
        response.raise_for_status()
        return self.parse_pages(response.text, chapter_url)

    # The three parsers below are pure and take markup, which is what lets the
    # whole template be tested from a recorded page with no network.

    def parse_search(self, html: str, titles: list[str]) -> list[Candidate]:
        ...

    def parse_chapters(self, html: str) -> list[ChapterRef]:
        ...

    def parse_pages(self, html: str, chapter_url: str) -> list[PageRef]:
        ...
```

Three rules for the parsers:

1. Score every candidate with `best_similarity(names, title)` from `app.text_utils`, the same helper
   `mangadex.py` uses, and return them sorted by score descending. A source that ranks differently
   from the others makes the merged review list meaningless.
2. A chapter number that will not parse is skipped, not defaulted. `mangadex.py` skips oneshots and
   unnumbered extras for the same reason: a chapter silently numbered 0 pollutes the range the
   download batch is built from. Catch `InvalidOperation` around `Decimal(...)`.
3. Every `PageRef` carries `{"Referer": chapter_url}`. That is the whole reason headers live on the
   page rather than on the source.

- [ ] **Step 5: Register the template**

In `backend/app/sources/registry.py`:

```python
from app.sources.templates.mangathemesia import MangaThemesiaSource

TEMPLATE_CLASSES: dict[str, type[TemplateSource]] = {
    "mangathemesia": MangaThemesiaSource,
}
```

- [ ] **Step 6: Seed the five catalogue rows**

`backend/alembic/versions/0013_seed_v1_sites.py`. Check the current head first — another branch may
have landed one — and set `down_revision` to whatever `python -m alembic heads` reports:

```python
"""seed the v1 sites

Revision ID: 0013_seed_v1_sites
Revises: 0012_seed_native_sources
Create Date: 2026-09-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013_seed_v1_sites"
down_revision: str | None = "0012_seed_native_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# All five land together even though only mangathemesia has a class today. A row
# whose template has no implementation is skipped by registry.reload with a log
# line saying so, which is the behaviour that lets the catalogue describe more
# than this deployment can currently run.
SITES = [
    ("thunderscans", "Thunder Scans", "mangathemesia", "https://en-thunderscans.com", False),
    ("vortexscans", "Vortex Scans", "iken", "https://vortexscans.org", False),
    ("orionscans", "Orion Scans", "iken", "https://orion-scans.com", False),
    ("mangageko", "MangaGeko", "native", "https://www.mgeko.cc", True),
    ("asurascans", "Asura Scans", "native", "https://asurascans.com", False),
]


def upgrade() -> None:
    for key, name, template, base_url, nsfw in SITES:
        op.execute(
            f"""
            insert into site_catalogue
                (key, name, template, base_url, lang, nsfw, overrides, version, hand_ported)
            values ('{key}', '{name}', '{template}', '{base_url}', 'en', {str(nsfw).lower()},
                    '{{}}'::jsonb, '1', true)
            on conflict (key) do nothing
            """
        )
        # Enabled on arrival: these are the sites this library downloads from,
        # and a site seeded disabled is one the user has to discover before it
        # does anything. The preference is theirs to turn off afterwards.
        op.execute(
            f"insert into source_pref (key, enabled) values ('{key}', true)"
            " on conflict (key) do nothing"
        )


def downgrade() -> None:
    keys = ", ".join(f"'{key}'" for key, *_ in SITES)
    op.execute(f"delete from source_pref where key in ({keys})")
    op.execute(f"delete from site_catalogue where key in ({keys})")
```

- [ ] **Step 7: Run the suite and ruff**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5438 .venv/bin/python -m pytest tests -q
.venv/bin/python -m ruff check app/ tests/
POSTGRES_HOST=localhost POSTGRES_PORT=5438 .venv/bin/python -m alembic heads
```

Expected: PASS, clean, and exactly **one** head. Two revisions sharing a parent take the API down on
boot and CI does not catch it.

- [ ] **Step 8: Commit, in two**

```bash
git add backend/app/sources/templates/mangathemesia.py backend/tests/test_template_mangathemesia.py backend/tests/fixtures/sources backend/app/sources/registry.py
git commit -m "feat(sources): port the mangathemesia template

Thunder Scans rides this template and is one of the sites this library
downloads from. Ported rather than transcribed: the parsers take markup and
return the contract's own types, so the whole template is tested from a
recorded page with no network.

A chapter number that will not parse is skipped rather than defaulted - a
chapter silently numbered 0 pollutes the range a download batch is built from."

git add backend/alembic/versions/0013_seed_v1_sites.py
git commit -m "feat(catalogue): seed the five v1 sites

All five land together although only mangathemesia has a class today. A row
whose template has no implementation is skipped at reload with a log line,
which is what lets the catalogue describe more than this deployment can run."
```

---

### Task 3: the `iken` template

**Files:**
- Create: `backend/app/sources/templates/iken.py`
- Create: `backend/tests/fixtures/sources/vortexscans_search.json`
- Create: `backend/tests/fixtures/sources/vortexscans_chapters.json`
- Create: `backend/tests/fixtures/sources/vortexscans_pages.json`
- Create: `backend/tests/test_template_iken.py`
- Modify: `backend/app/sources/registry.py`

**Interfaces:**
- Consumes: `TemplateSource` from Task 1.
- Produces: `IkenSource`, registered as `TEMPLATE_CLASSES["iken"]`. Serves catalogue keys `vortexscans` and `orionscans`, already seeded by Task 2.

**Read first:** `lib-multisrc/iken/` upstream — about 21 KB across the template, its DTOs and its
filters. The DTO file is the tell: this template talks to a JSON API rather than scraping markup, so
the fixtures are `.json` and the parsers take parsed objects, not HTML. Confirm that before you
record anything.

- [ ] **Step 1: Record the fixtures**

Find the API paths in the upstream template, then record one response each for search, chapter list
and page list from `https://vortexscans.org`, saving them as the three `.json` files above. Pretty-print
them so a diff is readable:

```bash
cd backend
curl -s -H "User-Agent: $UA" '<the search endpoint the template uses>' | python3 -m json.tool \
  > tests/fixtures/sources/vortexscans_search.json
```

- [ ] **Step 2: Write the failing test**

`backend/tests/test_template_iken.py`:

```python
"""Golden tests for the iken template.

JSON rather than markup, so these parsers take already-decoded payloads: the
same split mangadex.py uses, where parse_search and parse_feed are pure and the
request lives in the method that calls them.
"""

import json
from decimal import Decimal
from pathlib import Path

from app.sources.net import CatalogueRow
from app.sources.templates.iken import IkenSource

FIXTURES = Path(__file__).parent / "fixtures" / "sources"

ROW = CatalogueRow(key="vortexscans", base_url="https://vortexscans.org")


def _payload(name: str):
    return json.loads((FIXTURES / name).read_text())


def _source() -> IkenSource:
    return IkenSource(ROW, name="Vortex Scans", client=object())


def test_search_ranks_candidates_and_keeps_the_site_key():
    found = _source().parse_search(_payload("vortexscans_search.json"), ["Rebirth Monarch of the Dead"])

    assert found
    assert {c.source_site for c in found} == {"vortexscans"}
    assert all(c.source_url.startswith("https://") for c in found)
    assert found == sorted(found, key=lambda c: c.score, reverse=True)


def test_chapters_carry_decimal_numbers_and_absolute_urls():
    chapters = _source().parse_chapters(_payload("vortexscans_chapters.json"))

    assert chapters
    assert all(isinstance(c.number, Decimal) for c in chapters)
    assert all(c.url.startswith("https://") for c in chapters)


def test_pages_carry_a_referer_in_reading_order():
    chapter_url = "https://vortexscans.org/series/rebirth-monarch-of-the-dead/chapter-1"

    pages = _source().parse_pages(_payload("vortexscans_pages.json"), chapter_url)

    assert pages
    assert all(p.headers.get("Referer") == chapter_url for p in pages)
    assert all(p.url.startswith("https://") for p in pages)


def test_the_same_class_serves_a_second_site_from_its_own_row():
    # Two of the named sites ride this template. If the class has hardcoded
    # vortexscans anywhere, this is where it shows.
    orion = IkenSource(
        CatalogueRow(key="orionscans", base_url="https://orion-scans.com"),
        name="Orion Scans",
        client=object(),
    )

    found = orion.parse_search(_payload("vortexscans_search.json"), ["Rebirth"])

    assert {c.source_site for c in found} == {"orionscans"}
    assert all(c.source_url.startswith("https://orion-scans.com") for c in found)
```

- [ ] **Step 3: Run it and watch it fail**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5438 .venv/bin/python -m pytest tests/test_template_iken.py -q
```

Expected: FAIL, `ModuleNotFoundError: No module named 'app.sources.templates.iken'`.

- [ ] **Step 4: Write the template**

Same shape as Task 2, with `parse_search`, `parse_chapters` and `parse_pages` taking decoded JSON
rather than HTML:

```python
"""The iken template.

Ported from lib-multisrc/iken upstream. A JSON API rather than a scrape, which
is why the parsers here take decoded payloads - the same split mangadex.py uses.
"""

from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

from app.sources.base import Candidate, ChapterRef, PageRef
from app.sources.templates import TemplateSource
from app.text_utils import best_similarity


class IkenSource(TemplateSource):
    template: ClassVar[str] = "iken"
    overridable: ClassVar[frozenset[str]] = frozenset({"api_path", "series_path"})

    api_path: str = "/api"
    series_path: str = "/series"

    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]:
        ...

    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        ...

    async def list_pages(self, chapter_url: str, *, language: str = "en") -> list[PageRef]:
        ...

    def parse_search(self, payload: dict[str, Any], titles: list[str]) -> list[Candidate]:
        ...

    def parse_chapters(self, payload: dict[str, Any]) -> list[ChapterRef]:
        ...

    def parse_pages(self, payload: dict[str, Any], chapter_url: str) -> list[PageRef]:
        ...
```

The three rules from Task 2 hold here too: rank with `best_similarity`, skip a chapter number that
will not parse, and put `{"Referer": chapter_url}` on every page. One more applies to JSON
specifically: a chapter number may arrive as a string, or as an empty one — both MangaDex and
MangaBaka have done it — so parse defensively and skip rather than let an empty string reach a
`Decimal`.

Every URL this class builds must come from `self.base_url`, never a literal host. The fourth test
exists to catch exactly that.

- [ ] **Step 5: Register it**

```python
from app.sources.templates.iken import IkenSource

TEMPLATE_CLASSES: dict[str, type[TemplateSource]] = {
    "mangathemesia": MangaThemesiaSource,
    "iken": IkenSource,
}
```

- [ ] **Step 6: Run the full suite and ruff**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5438 .venv/bin/python -m pytest tests -q
.venv/bin/python -m ruff check app/ tests/
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/sources/templates/iken.py backend/tests/test_template_iken.py backend/tests/fixtures/sources backend/app/sources/registry.py
git commit -m "feat(sources): port the iken template

Vortex Scans and Orion Scans both ride it, so one port reaches two of the
sites this library downloads from. A JSON API rather than a scrape, so the
parsers take decoded payloads.

A test drives the class from a second catalogue row on purpose: every URL it
builds comes from base_url, and a hardcoded host would pass every other test
here."
```

---

### Task 4: MangaGeko, hand-written

**Files:**
- Create: `backend/app/sources/mangageko.py`
- Create: `backend/tests/fixtures/sources/mangageko_search.html`
- Create: `backend/tests/fixtures/sources/mangageko_chapters.html`
- Create: `backend/tests/fixtures/sources/mangageko_pages.html`
- Create: `backend/tests/test_source_mangageko.py`
- Modify: `backend/app/sources/registry.py` (`NATIVE_SOURCES`)

**Interfaces:**
- Consumes: `app.sources.base.Source`, `Candidate`, `ChapterRef`, `PageRef`; `app.sources.net.CatalogueRow`, `get_client`.
- Produces: `MangaGekoSource`, registered as `NATIVE_SOURCES["mangageko"]`. Its catalogue row was seeded in Task 2 with `template = 'native'`.

**Read first:** `src/en/mangarawclub/` upstream — the extension is named for an older domain, about
15 KB of Kotlin, and it is standalone rather than riding a template. That is why this is a plain
`Source` and not a `TemplateSource`: there is no second site to configure, so a class configured
from a row would buy nothing and cost an indirection.

- [ ] **Step 1: Record the fixtures**

Search, chapter list and one chapter's pages from `https://www.mgeko.cc`, into the three files
above. Trim each to the smallest page that still exercises the parser.

- [ ] **Step 2: Write the failing test**

`backend/tests/test_source_mangageko.py`. Follow `test_template_mangathemesia.py` from Task 2
exactly — the same three tests, with `MangaGekoSource` in place of `MangaThemesiaSource` and the
`mangageko_*.html` fixtures — plus one this site needs of its own:

```python
def test_a_chapter_with_no_usable_number_is_skipped_rather_than_numbered_zero():
    html = (FIXTURES / "mangageko_chapters.html").read_text()

    chapters = _source().parse_chapters(html)

    # Extras and specials carry no chapter number on this site. Numbering one 0
    # puts it at the head of every ascending range a download batch builds.
    assert all(c.number > 0 for c in chapters)
```

- [ ] **Step 3: Run it and watch it fail**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5438 .venv/bin/python -m pytest tests/test_source_mangageko.py -q
```

Expected: FAIL, `ModuleNotFoundError: No module named 'app.sources.mangageko'`.

- [ ] **Step 4: Write the source**

```python
"""MangaGeko (mgeko.cc).

Standalone upstream rather than a template leaf, so it is a plain Source: there
is no second site to configure and a class built from a catalogue row would buy
an indirection and nothing else.

Declared mixed content upstream. That belongs on the catalogue row as a content
warning, not in this module - what a site carries is a fact about the site, and
what the interface does with it is the settings screen's decision.
"""

from decimal import Decimal, InvalidOperation
from typing import ClassVar

from app.sources.base import Candidate, ChapterRef, PageRef, Source
from app.sources.net import CatalogueRow, get_client
from app.text_utils import best_similarity

SITE = "mangageko"
BASE_URL = "https://www.mgeko.cc"


class MangaGekoSource(Source):
    site: ClassVar[str] = SITE
    domains: ClassVar[tuple[str, ...]] = ("mgeko.cc", "mgeko.com")

    def __init__(self, client=None) -> None:
        # Built from the same catalogue row shape every other client uses, so
        # this site obeys its own rate limit rather than a default nobody set.
        self._client = client or get_client(CatalogueRow(key=SITE, base_url=BASE_URL))

    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]:
        ...

    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        ...

    async def list_pages(self, chapter_url: str, *, language: str = "en") -> list[PageRef]:
        ...

    def parse_search(self, html: str, titles: list[str]) -> list[Candidate]:
        ...

    def parse_chapters(self, html: str) -> list[ChapterRef]:
        ...

    def parse_pages(self, html: str, chapter_url: str) -> list[PageRef]:
        ...
```

`domains` carries the aliases because `source_for_url` checks them alongside the catalogue's
`base_url` — that is what lets a link pasted into Review from an older domain still resolve.

The three parser rules from Task 2 apply unchanged: rank with `best_similarity`, skip an unparseable
chapter number, and put `{"Referer": chapter_url}` on every page.

- [ ] **Step 5: Register it**

In `backend/app/sources/registry.py`:

```python
from app.sources.mangageko import MangaGekoSource

NATIVE_SOURCES: dict[str, Source] = {
    "mangadex": MangaDexSource(),
    "comick": ComickSource(*SITES[0]),
    "mangageko": MangaGekoSource(),
}
```

- [ ] **Step 6: Run the full suite and ruff, then commit**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5438 .venv/bin/python -m pytest tests -q
.venv/bin/python -m ruff check app/ tests/

git add backend/app/sources/mangageko.py backend/tests/test_source_mangageko.py backend/tests/fixtures/sources backend/app/sources/registry.py
git commit -m "feat(sources): add MangaGeko

One of the sites this library downloads from, and standalone upstream rather
than a template leaf - so a plain Source, since a class configured from a row
would buy an indirection and no second site.

Its older domains stay in the class's own domains tuple: source_for_url checks
those alongside the catalogue base_url, which is what lets a link pasted into
Review from the old host still resolve."
```

---

### Task 5: Asura Scans, hand-written

**Files:**
- Create: `backend/app/sources/asurascans.py`
- Create: `backend/tests/fixtures/sources/asurascans_search.json`
- Create: `backend/tests/fixtures/sources/asurascans_chapters.json`
- Create: `backend/tests/fixtures/sources/asurascans_pages.json`
- Create: `backend/tests/test_source_asurascans.py`
- Modify: `backend/app/sources/registry.py` (`NATIVE_SOURCES`)

**Interfaces:**
- Consumes: the same as Task 4.
- Produces: `AsuraScansSource`, registered as `NATIVE_SOURCES["asurascans"]`. Its catalogue row was seeded in Task 2.

**Read first:** `src/en/asurascans/` upstream — around 26 KB across the source, its DTOs and its
filters. The DTO file means JSON, so the fixtures are `.json` and the parsers take decoded payloads,
the same as Task 3 rather than Task 4.

- [ ] **Step 1: Record the three JSON fixtures**

From `https://asurascans.com`, pretty-printed, into the three files above.

- [ ] **Step 2: Write the failing test**

`backend/tests/test_source_asurascans.py`. Follow `test_template_iken.py` from Task 3 — the first
three tests, with `AsuraScansSource` and the `asurascans_*.json` fixtures. Drop its fourth test: that
one exists because two sites share the `iken` class, and nothing shares this one.

Add the string-number case, because this is a JSON source:

```python
def test_a_chapter_number_arriving_as_a_string_still_parses():
    payload = _payload("asurascans_chapters.json")

    chapters = _source().parse_chapters(payload)

    assert chapters
    assert all(isinstance(c.number, Decimal) for c in chapters)
```

- [ ] **Step 3: Run it and watch it fail, then write the source**

Same shape as Task 4's class, with JSON parsers taking decoded payloads. `domains` is `()` — this
site has no alias worth carrying, and an empty tuple says so rather than a guess.

- [ ] **Step 4: Register it, run the suite, commit**

```python
from app.sources.asurascans import AsuraScansSource

NATIVE_SOURCES: dict[str, Source] = {
    "mangadex": MangaDexSource(),
    "comick": ComickSource(*SITES[0]),
    "mangageko": MangaGekoSource(),
    "asurascans": AsuraScansSource(),
}
```

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5438 .venv/bin/python -m pytest tests -q
.venv/bin/python -m ruff check app/ tests/

git add backend/app/sources/asurascans.py backend/tests/test_source_asurascans.py backend/tests/fixtures/sources backend/app/sources/registry.py
git commit -m "feat(sources): add Asura Scans

The last of the four v1 sites, standalone upstream and a JSON API, so its
parsers take decoded payloads rather than markup.

A chapter number arriving as a string is the case with its own test: both
MangaDex and MangaBaka have sent one, and an empty string reaching a Decimal
fails far from the parser that let it through."
```

---

### Task 6: fan `match_search` out across every enabled source

**Files:**
- Modify: `backend/app/handlers/match_search.py`
- Modify: `backend/app/settings_store.py`
- Modify: `backend/app/api/routes_settings.py` (`EDITABLE`)
- Test: `backend/tests/test_match_search_fanout.py`

**Interfaces:**
- Consumes: `all_sources()` from the registry, now returning up to five sources instead of two.
- Produces: settings keys `source_search_concurrency` (default `4`) and `source_search_timeout` (default `20`), which Task 8 renders as fields.

**Why this task exists:** the handler loops sources one at a time today. With five enabled that is
five round trips in series, and one site that hangs holds the job lease until it expires — taking
the other four's candidates with it, because nothing is stored until the loop finishes.

- [ ] **Step 1: Add the two settings**

In `backend/app/settings_store.py`, add the key constants next to the others:

```python
SOURCE_SEARCH_CONCURRENCY = "source_search_concurrency"
SOURCE_SEARCH_TIMEOUT = "source_search_timeout"
```

to the `Defaults` dataclass:

```python
    # Four at once against five sites: enough that a search is one round trip
    # rather than five, low enough that a series never has more sockets open
    # than a homelab's connection tracking enjoys.
    source_search_concurrency: int = 4
    # Well under the job lease, deliberately. A source that has not answered in
    # twenty seconds is not about to, and the whole point of the timeout is that
    # its silence costs the other sources nothing.
    source_search_timeout: int = 20
```

to `_fallback`:

```python
        case k if k == SOURCE_SEARCH_CONCURRENCY:
            return str(DEFAULTS.source_search_concurrency)
        case k if k == SOURCE_SEARCH_TIMEOUT:
            return str(DEFAULTS.source_search_timeout)
```

and to the `keys` list in `all_settings`. Then add both to `EDITABLE` in
`backend/app/api/routes_settings.py`.

- [ ] **Step 2: Write the failing test**

`backend/tests/test_match_search_fanout.py`:

```python
"""The fan-out's three promises: bounded, timed out, and partial.

Every source here is a fake. The point is the handler's behaviour when one
source is slow, one is broken and one works - which is not something a real
site can be asked to demonstrate on command.
"""

import asyncio

import pytest
from sqlalchemy import text

from app.handlers import match_search
from app.sources.base import Candidate


class FakeSource:
    def __init__(self, site, *, delay=0.0, fail=False, score=0.5):
        self.site = site
        self.domains = ()
        self._delay = delay
        self._fail = fail
        self._score = score

    async def search(self, titles, *, limit=8):
        await asyncio.sleep(self._delay)
        if self._fail:
            raise RuntimeError("the site answered with nonsense")
        return [
            Candidate(
                source_site=self.site,
                source_url=f"https://{self.site}.test/title/1",
                title=titles[0],
                score=self._score,
            )
        ]


async def _series(session, title="Rebirth Monarch of the Dead") -> int:
    row = await session.execute(
        text("insert into series (canonical_title) values (:t) returning id"), {"t": title}
    )
    return int(row.scalar_one())


async def test_a_hanging_source_does_not_cost_the_others_their_candidates(
    session, monkeypatch, job_context
):
    series_id = await _series(session)
    monkeypatch.setattr(
        match_search,
        "all_sources",
        lambda: [
            FakeSource("fast", score=0.9),
            FakeSource("slow", delay=5.0),
            FakeSource("broken", fail=True),
        ],
    )
    await session.execute(
        text("insert into setting (key, value) values ('source_search_timeout', '1')")
    )

    await match_search.handle(job_context(series_id=series_id))

    stored = (
        await session.execute(
            text("select source_site from series_candidate where series_id = :s"),
            {"s": series_id},
        )
    ).scalars().all()
    # The one working source's candidate is kept. Before the fan-out, the slow
    # source held the whole handler and nothing was stored at all.
    assert stored == ["fast"]


async def test_every_failure_is_named_in_the_job_log(session, monkeypatch, job_context):
    series_id = await _series(session)
    monkeypatch.setattr(
        match_search,
        "all_sources",
        lambda: [FakeSource("fast"), FakeSource("broken", fail=True)],
    )
    ctx = job_context(series_id=series_id)

    await match_search.handle(ctx)

    # The review screen has to be able to say which source did not answer;
    # a silent failure reads as "this site has nothing", which is a different
    # claim.
    assert any("broken" in line for line in ctx.logged)


async def test_priority_breaks_a_tie_between_equal_scores(session, monkeypatch, job_context):
    series_id = await _series(session)
    monkeypatch.setattr(
        match_search,
        "all_sources",
        lambda: [FakeSource("second", score=0.7), FakeSource("first", score=0.7)],
    )
    for key, priority in (("first", 10), ("second", 90)):
        await session.execute(
            text("insert into source_pref (key, enabled, priority) values (:k, true, :p)"),
            {"k": key, "p": priority},
        )

    await match_search.handle(job_context(series_id=series_id))

    ordered = (
        await session.execute(
            text(
                "select source_site from series_candidate"
                " where series_id = :s order by score desc, id"
            ),
            {"s": series_id},
        )
    ).scalars().all()
    assert ordered[0] == "first"
```

`job_context` is a fixture. If `backend/tests/conftest.py` has no equivalent, add one that builds a
`JobContext` with the given payload and records every `ctx.log` call on a `logged` list.

- [ ] **Step 3: Run it and watch it fail**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5438 .venv/bin/python -m pytest tests/test_match_search_fanout.py -q
```

Expected: FAIL — the sequential loop stores nothing when a source hangs, and ignores priority.

- [ ] **Step 4: Rewrite the fan-out**

Replace the `for source in all_sources()` loop in `handle` with:

```python
async def source_priorities(session: AsyncSession) -> dict[str, int]:
    """source_pref.priority, read here rather than carried on the registry.

    A handler may touch the database and `sources/` may not, so the ranking
    tiebreak is read where it is used instead of being threaded through the
    registry for one caller.
    """
    rows = (await session.execute(text("select key, priority from source_pref"))).all()
    return {key: priority for key, priority in rows}


async def _search_one(
    source: Source, titles: list[str], timeout: float, gate: asyncio.Semaphore, ctx: JobContext
) -> list[Candidate]:
    """One source's search, bounded and timed out, never raising.

    Returning an empty list on failure rather than propagating is what makes the
    result partial instead of all-or-nothing: one dead site must not cost the
    other four their candidates.
    """
    async with gate:
        try:
            found = await asyncio.wait_for(source.search(titles), timeout)
        except TimeoutError:
            await ctx.log(f"{source.site}: no answer in {timeout:.0f}s", level="warning")
            return []
        except Exception as exc:  # noqa: BLE001 - one dead source must not kill the search
            await ctx.log(f"{source.site} search failed: {exc}", level="warning")
            return []
    await ctx.log(f"{source.site}: {len(found)} candidates")
    return found
```

and in `handle`:

```python
    concurrency = await settings_store.get_int(
        ctx.session, settings_store.SOURCE_SEARCH_CONCURRENCY
    )
    timeout = await settings_store.get_int(ctx.session, settings_store.SOURCE_SEARCH_TIMEOUT)
    priorities = await source_priorities(ctx.session)

    gate = asyncio.Semaphore(max(1, concurrency))
    results = await asyncio.gather(
        *(_search_one(source, titles, timeout, gate, ctx) for source in all_sources())
    )
    candidates = [candidate for found in results for candidate in found]

    # Score first, source priority as the tiebreak. Two sites carrying the same
    # title score identically far more often than they differ, so without the
    # tiebreak the order is whichever coroutine happened to finish first.
    candidates.sort(key=lambda c: (-c.score, priorities.get(c.source_site, 100)))
    await store_candidates(ctx.session, series_id, candidates[:20])
```

`store_candidates` already deletes and re-inserts, so a partial result replaces the previous one
wholesale — which is what you want when one source was silent this time and answered last time.

- [ ] **Step 5: Run the whole suite, ruff, commit**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5438 .venv/bin/python -m pytest tests -q
.venv/bin/python -m ruff check app/ tests/

git add backend/app/handlers/match_search.py backend/app/settings_store.py backend/app/api/routes_settings.py backend/tests/test_match_search_fanout.py backend/tests/conftest.py
git commit -m "feat(handlers): search every enabled source at once

The loop ran sources in series and stored nothing until it finished, so one
site that hung held the job lease and took the other sources' candidates with
it. Now each search is bounded by a semaphore and a timeout, failures are
logged per source and return empty, and whatever answered is stored.

Score still ranks; source priority breaks the tie. Two sites carrying the
same title score identically more often than not, and without the tiebreak
the order was whichever coroutine finished first."
```

---

### Task 7: `/api/sources` — serve and toggle the catalogue

**Files:**
- Create: `backend/app/api/routes_sources.py`
- Modify: `backend/app/api/main.py`
- Test: `backend/tests/test_routes_sources.py`

**Interfaces:**
- Consumes: `app.sources.registry.TEMPLATE_CLASSES` and `NATIVE_SOURCES` (to say why a row cannot run), `app.sources.registry.reload`.
- Produces: `GET /api/sources` returning `{"items": [...], "total": int, "page": int, "size": int}`, each item `{key, name, template, base_url, lang, nsfw, hand_ported, version, enabled, priority, reason}`; `PUT /api/sources/{key}` taking `{"enabled": bool}` and returning the updated item. Task 8 consumes both.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_routes_sources.py`:

```python
"""The catalogue as the settings screen sees it."""

import pytest
from sqlalchemy import text


async def _seed(session):
    await session.execute(
        text(
            """
            insert into site_catalogue
                (key, name, template, base_url, lang, nsfw, overrides, version, hand_ported)
            values ('thunderscans', 'Thunder Scans', 'mangathemesia', 'https://t.test', 'en',
                    false, '{}'::jsonb, '1', true),
                   ('nihonsite', 'Nihon Site', 'madara', 'https://n.test', 'ja',
                    true, '{}'::jsonb, '1', false)
            on conflict (key) do nothing
            """
        )
    )
    await session.execute(
        text("insert into source_pref (key, enabled) values ('thunderscans', true)"
             " on conflict (key) do nothing")
    )


async def test_the_listing_pages_and_reports_the_real_total(client, session):
    await _seed(session)

    body = (await client.get("/api/sources?size=1")).json()

    assert len(body["items"]) == 1
    # The screen must not report its page as the total: 1390 rows do not go on
    # one page, and a count of what fitted is a different number.
    assert body["total"] >= 2
    assert body["size"] == 1


async def test_a_row_that_cannot_run_says_why(client, session):
    await _seed(session)

    items = {i["key"]: i for i in (await client.get("/api/sources")).json()["items"]}

    # Two different reasons, and neither is invented by the screen.
    assert items["nihonsite"]["reason"] == "not hand-ported"
    assert items["thunderscans"]["reason"] is None


async def test_filters_narrow_by_language_and_content_warning(client, session):
    await _seed(session)

    japanese = (await client.get("/api/sources?lang=ja")).json()["items"]
    safe = (await client.get("/api/sources?nsfw=false")).json()["items"]

    assert {i["key"] for i in japanese} == {"nihonsite"}
    assert "nihonsite" not in {i["key"] for i in safe}


async def test_toggling_a_source_persists_and_reloads_the_registry(client, session):
    await _seed(session)

    response = await client.put("/api/sources/nihonsite", json={"enabled": True})

    assert response.status_code == 200
    assert response.json()["enabled"] is True
    stored = (
        await session.execute(
            text("select enabled from source_pref where key = 'nihonsite'")
        )
    ).scalar_one()
    assert stored is True


async def test_toggling_a_site_the_catalogue_does_not_carry_is_a_404(client):
    response = await client.put("/api/sources/no-such-site", json={"enabled": True})

    assert response.status_code == 404
    # Asserts the handler's own words, so this test fails if the route is
    # deleted rather than passing on FastAPI's default.
    assert "no-such-site" in response.json()["detail"]
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5438 .venv/bin/python -m pytest tests/test_routes_sources.py -q
```

Expected: FAIL, 404 on every request — the router does not exist.

- [ ] **Step 3: Write the route**

`backend/app/api/routes_sources.py`:

```python
"""The source catalogue, as the settings screen reads and writes it.

Paged because the catalogue is generated and grows to four figures: a listing
that returns everything would be the one request on this screen that gets slower
every time the generator runs.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.sources import registry

router = APIRouter(prefix="/api/sources", tags=["sources"])

Session = Annotated[AsyncSession, Depends(db_session)]

MAX_PAGE_SIZE = 100

FILTERS = """
    (cast(:q as text) is null
        or c.name ilike '%' || cast(:q as text) || '%'
        or c.key ilike '%' || cast(:q as text) || '%')
    and (cast(:lang as text) is null or c.lang = cast(:lang as text))
    and (cast(:nsfw as boolean) is null or c.nsfw = cast(:nsfw as boolean))
    and (cast(:enabled as boolean) is null
        or coalesce(p.enabled, false) = cast(:enabled as boolean))
"""


class SourceIn(BaseModel):
    enabled: bool


def _reason(row: Any) -> str | None:
    """Why this row cannot run, in the screen's own words - or None if it can.

    Computed here rather than on the screen: the screen has no way to know which
    templates this deployment implements, and a row disabled for a reason nobody
    states reads as a bug in the toggle.
    """
    if row["disabled_reason"]:
        return row["disabled_reason"]
    if not row["hand_ported"]:
        return "not hand-ported"
    if row["template"] == "native":
        return None if row["key"] in registry.NATIVE_SOURCES else "no implementation for this site"
    if row["template"] not in registry.TEMPLATE_CLASSES:
        return f"no implementation for the {row['template']} template"
    return None


def _item(row: Any) -> dict[str, Any]:
    return {
        "key": row["key"],
        "name": row["name"],
        "template": row["template"],
        "base_url": row["base_url"],
        "lang": row["lang"],
        "nsfw": row["nsfw"],
        "hand_ported": row["hand_ported"],
        "version": row["version"],
        "enabled": row["enabled"],
        "priority": row["priority"],
        "reason": _reason(row),
    }


SELECT_ONE = """
    select c.key, c.name, c.template, c.base_url, c.lang, c.nsfw, c.hand_ported, c.version,
           coalesce(p.enabled, false) as enabled,
           coalesce(p.priority, 100) as priority,
           p.disabled_reason
      from site_catalogue c
      left join source_pref p on p.key = c.key
"""


@router.get("")
async def list_sources(
    session: Session,
    q: str | None = None,
    lang: str | None = None,
    nsfw: bool | None = None,
    enabled: bool | None = None,
    page: int = 1,
    size: int = 50,
) -> dict[str, Any]:
    size = max(1, min(size, MAX_PAGE_SIZE))
    page = max(1, page)
    params = {"q": q, "lang": lang, "nsfw": nsfw, "enabled": enabled}

    total = (
        await session.execute(
            text(
                "select count(*) from site_catalogue c"
                " left join source_pref p on p.key = c.key"
                f" where {FILTERS}"
            ),
            params,
        )
    ).scalar_one()

    rows = (
        await session.execute(
            text(f"{SELECT_ONE} where {FILTERS} order by c.name limit :size offset :offset"),
            {**params, "size": size, "offset": (page - 1) * size},
        )
    ).mappings().all()

    return {"items": [_item(row) for row in rows], "total": total, "page": page, "size": size}


@router.put("/{key}")
async def set_source(key: str, body: SourceIn, session: Session) -> dict[str, Any]:
    exists = (
        await session.execute(
            text("select 1 from site_catalogue where key = :key"), {"key": key}
        )
    ).first()
    if not exists:
        raise HTTPException(status_code=404, detail=f"the catalogue has no site {key}")

    await session.execute(
        text(
            """
            insert into source_pref (key, enabled) values (:key, :enabled)
            on conflict (key) do update set enabled = excluded.enabled
            """
        ),
        {"key": key, "enabled": body.enabled},
    )
    await session.commit()

    # Enabling a site in settings *is* registering it (app/sources/registry.py),
    # so the registry is rebuilt here rather than at the next boot - otherwise
    # the toggle reports success and nothing searches the site until a restart.
    await registry.reload(session)

    row = (
        await session.execute(text(f"{SELECT_ONE} where c.key = :key"), {"key": key})
    ).mappings().one()
    return _item(row)
```

- [ ] **Step 4: Register the router**

In `backend/app/api/main.py`, add `routes_sources` to the `from app.api import (...)` block and
`app.include_router(routes_sources.router)` beside the others.

- [ ] **Step 5: Run the suite, ruff, commit**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5438 .venv/bin/python -m pytest tests -q
.venv/bin/python -m ruff check app/ tests/

git add backend/app/api/routes_sources.py backend/app/api/main.py backend/tests/test_routes_sources.py
git commit -m "feat(api): serve and toggle the source catalogue

Paged, because the catalogue is generated output that grows to four figures
and a listing returning all of it is the one request on this screen that gets
slower every regeneration.

Why a row cannot run is computed here, not on the screen: the screen has no
way to know which templates this deployment implements, and a row disabled
for a reason nobody states reads as a broken toggle.

The toggle reloads the registry rather than waiting for the next boot -
enabling a site in settings is what registering it means now."
```

---

### Task 8: the sources panel in Settings

**Files:**
- Create: `frontend/src/features/settings/useSources.ts`
- Create: `frontend/src/features/settings/SourcesPanel.tsx`
- Create: `frontend/src/features/settings/SourceRow.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/features/settings/SettingsPage.tsx`
- Modify: `frontend/src/features/settings/PipelineFields.tsx`

**Interfaces:**
- Consumes: `GET /api/sources` and `PUT /api/sources/{key}` from Task 7; `lib/useAsyncData.ts`, `lib/useNotice.ts`; `ui/` primitives `Card`, `Toggle`, `Badge`, `Chip`, `Button`, `EmptyState`, `ErrorState`, `Skeleton`.
- Produces: nothing other screens consume — this panel lives inside Settings and is not imported elsewhere.

- [ ] **Step 1: Add the client calls**

In `frontend/src/lib/api.ts`, beside the existing exports:

```ts
export interface Source {
  key: string
  name: string
  template: string
  base_url: string
  lang: string
  nsfw: boolean
  hand_ported: boolean
  version: string
  enabled: boolean
  priority: number
  /** Why this row cannot run, in the API's words. Null when it can. */
  reason: string | null
}

export interface SourcePage {
  items: Source[]
  total: number
  page: number
  size: number
}
```

and on the `api` object:

```ts
  sources: (params: { q?: string; lang?: string; nsfw?: boolean; enabled?: boolean; page?: number }) => {
    const query = new URLSearchParams()
    if (params.q) query.set('q', params.q)
    if (params.lang) query.set('lang', params.lang)
    if (params.nsfw !== undefined) query.set('nsfw', String(params.nsfw))
    if (params.enabled !== undefined) query.set('enabled', String(params.enabled))
    query.set('page', String(params.page ?? 1))
    return request<SourcePage>(`/api/sources?${query}`)
  },
  setSourceEnabled: (key: string, enabled: boolean) =>
    request<Source>(`/api/sources/${key}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    }),
```

- [ ] **Step 2: Write the hook**

`frontend/src/features/settings/useSources.ts`:

```ts
import { useCallback, useState } from 'react'

import { api, type Source } from '../../lib/api'
import { useAsyncData } from '../../lib/useAsyncData'
import { useNotice } from '../../lib/useNotice'

export function useSources() {
  const [query, setQuery] = useState('')
  const [lang, setLang] = useState('')
  const [page, setPage] = useState(1)
  const [busy, setBusy] = useState<string | null>(null)
  const { notice, report, reportFailure, clear } = useNotice()

  const load = useCallback(
    () => api.sources({ q: query || undefined, lang: lang || undefined, page }),
    [query, lang, page],
  )
  const { data, error, reload } = useAsyncData(load)

  const toggle = useCallback(
    async (source: Source) => {
      setBusy(source.key)
      clear()
      try {
        const updated = await api.setSourceEnabled(source.key, !source.enabled)
        report(
          updated.enabled
            ? `${updated.name} is now searched when a series needs matching.`
            : `${updated.name} will no longer be searched.`,
        )
        reload()
      } catch (failure) {
        reportFailure(failure)
      } finally {
        setBusy(null)
      }
    },
    [clear, reload, report, reportFailure],
  )

  // Searching or filtering has to return to the first page: page 4 of a
  // narrowed result is usually empty, and an empty page reads as "no sites
  // match" rather than "you are past the end".
  const search = useCallback((value: string) => {
    setQuery(value)
    setPage(1)
  }, [])

  const filterLanguage = useCallback((value: string) => {
    setLang(value)
    setPage(1)
  }, [])

  return {
    items: data?.items ?? [],
    total: data?.total ?? 0,
    page: data?.page ?? 1,
    size: data?.size ?? 50,
    loaded: data !== null,
    error,
    reload,
    notice,
    busy,
    query,
    lang,
    search,
    filterLanguage,
    setPage,
    toggle,
  }
}
```

- [ ] **Step 3: Write the row**

`frontend/src/features/settings/SourceRow.tsx`. One component, presentational, no fetching:

```tsx
import { Badge, Toggle } from '../../ui'
import type { Source } from '../../lib/api'

export function SourceRow({
  source,
  busy,
  onToggle,
}: {
  source: Source
  busy: boolean
  onToggle: () => void
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-space-sm border-b border-outline-variant py-space-sm last:border-b-0">
      <div className="min-w-0">
        <div className="flex items-center gap-space-xs">
          <span className="text-body-md text-on-surface">{source.name}</span>
          {/* The content warning is a badge, not a reason to hide the row: two
              of the sites this library depends on are declared mixed upstream. */}
          {source.nsfw && <Badge tone="warning">18+</Badge>}
        </div>
        <span className="font-mono text-label-sm text-on-surface-variant">
          {source.base_url} · {source.template} · {source.lang}
        </span>
        {source.reason && (
          <p className="text-label-sm text-on-surface-variant">{source.reason}</p>
        )}
      </div>
      <Toggle
        checked={source.enabled}
        disabled={busy || source.reason !== null}
        onChange={onToggle}
        label={source.enabled ? 'Enabled' : 'Disabled'}
      />
    </div>
  )
}
```

Check `ui/Toggle.tsx` and `ui/Badge.tsx` for their real prop names before writing this — the shapes
above are what the row needs, not necessarily what they already take. If `Badge` has no `warning`
tone, use the tone it does have rather than adding one.

- [ ] **Step 4: Write the panel**

`frontend/src/features/settings/SourcesPanel.tsx`. It renders four distinguishable states — the
reason `useAsyncData` exists — plus search, a language filter and paging:

- `!loaded && !error` → `Skeleton`
- `error && !loaded` → `ErrorState` with a retry calling `reload`
- `error && loaded` → the list, with a `NoticeBar` saying the refresh failed
- `loaded && items.length === 0` → `EmptyState`, whose copy says no site matches the filters, **not**
  that no site exists
- otherwise the list, with `Showing {items.length} of {total}` and previous/next buttons

Every figure comes from the API. Do not compute a page count the API does not serve — `total` and
`size` are both in the response, so `Math.ceil(total / size)` is derived from served numbers and is
fine; a "sites working" count is not, because nothing serves it.

- [ ] **Step 5: Mount it, and add the two search fields**

In `SettingsPage.tsx`, render `<SourcesPanel />` as its own section. In `PipelineFields.tsx`, add
number fields for `source_search_concurrency` and `source_search_timeout` next to
`per_source_concurrency`, and add both keys to `DEFAULT_VALUES` in `useSettings.ts` with `'4'` and
`'20'` — that map mirrors the backend's `Defaults` dataclass and drifts silently if it is not updated
alongside it.

- [ ] **Step 6: Build, and verify every class you introduced is real**

```bash
cd frontend
npm run build
grep -o 'border-outline-variant' dist/assets/*.css
grep -o 'gap-space-xs' dist/assets/*.css
```

Do this for **every** class the three new files introduce. A class that typechecks, builds clean and
generates nothing has happened three times on this codebase. Escaped selectors need literal
matching — a regex misses the backslash. Report what you grepped and what you found.

- [ ] **Step 7: Look at it**

```bash
docker compose build api web && docker compose up -d --force-recreate api worker web
```

Open Settings at `http://localhost:8080` and check, at 1280 and at 390 wide:

- the list pages, searches and filters against the real catalogue
- a disabled row states its reason and its toggle is not clickable
- toggling a site reports what changed, and the row stays changed after a reload
- nothing overlaps the bottom navigation at 390

Defects on this branch's predecessor were found by running the app, not by reading the diff. Eight of
them, none visible in a review.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/features/settings frontend/src/lib/api.ts
git commit -m "feat(web): manage sources from Settings

Search, language filter and paging against the real catalogue, which is
generated output and grows to four figures - the screen must not report its
page as the total.

A row that cannot run states the API's reason and its toggle is inert. A
site's content warning is a badge rather than grounds for hiding it: two of
the sites this library depends on are declared mixed upstream, and hiding
them by default reads as the port having failed."
```

---

## Self-review

**Spec coverage.** Source contract, per-site client, fetcher, archive writer and the catalogue tables
are already on `main` and are not re-planned here. This plan covers the spec's *Which sites v1
reaches* section (Tasks 2–5), its *Matching* section (Task 6) and its *Interface* section (Tasks 7–8).

Three spec sections are deliberately **not** in this plan, each with an open issue of its own:

- The catalogue generator and its CI guard (#100, #101). Task 2 seeds five rows by migration instead.
  That is what lets the screen and the fan-out be built and used now; the generator later replaces
  those five with the hundreds the templates actually reach. `replace_catalogue` already refuses an
  empty catalogue and scopes its deletes away from `native` rows, so the generator arriving does not
  disturb the hand-written sites.
- FlareSolverr (#92), the handler convergence (#95), the MangaDex and comick ports (#96, #97) and
  deleting the binary (#98). A site that turns out to sit behind a Cloudflare challenge will fail its
  fixture recording in Task 2 or 3; report that and stop rather than working around it.
- Comix (#135), whose descrambler is its own round.

**Type consistency.** `TemplateSource.__init__` takes `(row, *, name, lang, overrides, client)` in
Task 1 and is called that way in Tasks 2 and 3. `CatalogueRow` is `app.sources.net`'s, with
`key`, `base_url`, `rate_limit`, `rate_limit_override` — the four fields Task 1's registry passes.
Parsers are `parse_search` / `parse_chapters` / `parse_pages` in every source module, taking markup
in Tasks 2 and 4 and decoded payloads in Tasks 3 and 5. The API's item keys in Task 7 are the
`Source` interface's fields in Task 8, `reason` included.

**Known gap, stated rather than hidden.** The selector strings and API paths for the four ports are
not in this plan. They come from the upstream file and the fixture the implementer records, and
writing them here would be guessing at markup neither the plan's author nor its reader has looked at.
Every other part of those tasks — class shape, attribute names, method signatures, fixtures, test
assertions and commit messages — is specified.
