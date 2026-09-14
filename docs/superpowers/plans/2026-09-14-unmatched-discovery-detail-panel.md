# Unmatched and Discovery Detail Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Selecting a row on Unmatched or a card on Discovery opens a detail panel beside the list, the way selecting a series in the library opens its detail — without navigating away from a filtered, paged list or interrupting the search-and-add flow.

**Architecture:** One shared panel shell in `ui/`, two feature-owned bodies. The shell is a sticky column on `lg` and above and a bottom sheet below it, so the same component serves a desktop two-pane layout and a phone. Discovery needs no new endpoint — `GET /api/suggestions` already serves each suggestion's sources, best source, reason chain and per-target write results, and the card renders only a fraction of it. Unmatched needs one: the list payload deliberately carries only what a row shows, and the panel wants every spelling the anime is known by, each provider's own row, and the relations that were declared but could not be used.

**Tech Stack:** FastAPI + SQLAlchemy async + Postgres; React 18 + TypeScript + Vite + Tailwind.

**Spec:** `docs/superpowers/specs/2026-09-13-anime-manga-discovery-design.md` and the maintainer's request of 2026-09-14: "assim como no library que quando seleciono um manga ele mostra detalhes, quero o mesmo no unmatched e discovery", answered with a side panel on the same screen.

## Global Constraints

- Everything committed is in **English**: code, comments, commit messages, the interface.
- No commit, PR, issue or comment may reference the tools used to write it. No trailers.
- Micro commits, imperative scoped subjects (`feat(api):`, `feat(web):`).
- **No screen renders a number the API cannot serve.**
- `frontend/tailwind.config.ts` is the only place a colour, size, radius or spacing value lives.
- A Tailwind class is only real if the built CSS contains it — `npm run build`, then `grep` over `frontend/dist/`.
- **Feature folders never import from each other.** The panel shell therefore lives in `ui/`, and `features/unmatched/` and `features/discovery/` each own their own body.
- A screen's own data goes through `lib/useAsyncData.ts`.
- Backend tests: `POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests -q` from `backend/`. Lint: `.venv/bin/python -m ruff check app/ tests/`.
- There is no test runner in `frontend/` — verification is `npm run build` (which runs `tsc -b`), a `grep` over `dist/`, and exercising the screen in the running stack.

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/api/routes_discovery.py` *(modify)* | `GET /api/discovery/unmatched/{anime_id}` — the panel's payload. |
| `backend/tests/test_discovery_unmatched.py` *(modify)* | The new endpoint's cases. |
| `frontend/src/ui/DetailPanel.tsx` *(create)* | The shell: sticky column on `lg`, bottom sheet below, a close control, Escape to dismiss. |
| `frontend/src/ui/index.ts` *(modify)* | Export it. |
| `frontend/src/lib/api.ts` *(modify)* | `UnmatchedDetail` type and `api.unmatchedDetail`. |
| `frontend/src/features/unmatched/UnmatchedDetail.tsx` *(create)* | The panel's body for an anime. |
| `frontend/src/features/unmatched/UnmatchedPage.tsx` *(modify)* | Selection state and the two-pane layout. |
| `frontend/src/features/unmatched/AnimeRow.tsx` *(modify)* | Rows become selectable and mark the selected one. |
| `frontend/src/features/discovery/SuggestionDetail.tsx` *(create)* | The panel's body for a suggestion. |
| `frontend/src/features/discovery/DiscoveryPage.tsx` *(modify)* | Selection state and the two-pane layout. |
| `frontend/src/features/discovery/SuggestionCard.tsx` *(modify)* | Cards become selectable and mark the selected one. |

---

## Task 1: Serve an unmatched anime's own detail

**Files:**
- Modify: `backend/app/api/routes_discovery.py`
- Test: `backend/tests/test_discovery_unmatched.py`

**Interfaces:**
- Consumes: `_load_anime(session, anime_id)` and `anime_payload(anime)`, both already in the module.
- Produces: `GET /api/discovery/unmatched/{anime_id}` answering the row payload plus `{"synonyms": [...], "members": [{"provider", "media_id", "url"}], "related": [{"provider", "media_id", "relation", "title", "format", "usable"}]}`. Task 3 types and renders it.

The list payload carries what a row shows and no more, on purpose: five hundred rows paged at fifty would otherwise carry five hundred relation lists. The panel is one anime, so it can afford the rest.

`related` is the point of the screen. These anime are the ones no relation could turn into a manga, and the panel is where the user finds out *why*: a declared relation exists but its format is a light novel, or no relation was declared at all. `usable` is false for anything outside `MANGA_FORMATS` — the same set `app/providers/base.py` uses to keep a light novel from being offered as a download.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_discovery_unmatched.py`:

```python
async def test_the_detail_carries_every_spelling_and_every_provider_row(client):
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into anime_entry
                       (provider, provider_media_id, title_romaji, title_english,
                        synonyms, status, progress_episode, total_episodes,
                        related_manga, raw)
                values ('anilist', '21', 'Tousou Kikou', 'Escape Machine',
                        '["逃走機構"]'::jsonb, 'reading', 12, 24,
                        '[]'::jsonb, '{}'::jsonb)
                """
            )
        )
        await session.commit()

    row = (await client.get("/api/discovery/unmatched")).json()["items"][0]
    body = (await client.get(f"/api/discovery/unmatched/{row['id']}")).json()

    assert body["title_english"] == "Escape Machine"
    assert "逃走機構" in body["synonyms"]
    assert body["members"] == [
        {
            "provider": "anilist",
            "media_id": "21",
            "url": "https://anilist.co/anime/21",
        }
    ]


async def test_a_declared_relation_that_is_not_a_manga_says_so(client):
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into anime_entry
                       (provider, provider_media_id, title_romaji, title_english,
                        synonyms, status, progress_episode, total_episodes,
                        related_manga, raw)
                values ('anilist', '21', 'Tousou Kikou', 'Escape Machine',
                        '[]'::jsonb, 'reading', 12, 24, :related, '{}'::jsonb)
                """
            ),
            {
                "related": json.dumps(
                    [
                        {
                            "provider": "anilist",
                            "media_id": "900",
                            "relation": "SOURCE",
                            "title": "Escape Machine (Light Novel)",
                            "format": "NOVEL",
                        }
                    ]
                )
            },
        )
        await session.commit()

    row = (await client.get("/api/discovery/unmatched")).json()["items"][0]
    body = (await client.get(f"/api/discovery/unmatched/{row['id']}")).json()

    # The whole reason this anime is on the unmatched screen: a relation was
    # declared, and it points at something the downloader can never fetch.
    assert body["related"] == [
        {
            "provider": "anilist",
            "media_id": "900",
            "relation": "SOURCE",
            "title": "Escape Machine (Light Novel)",
            "format": "NOVEL",
            "usable": False,
        }
    ]


async def test_a_detail_for_a_missing_anime_is_a_404(client):
    response = await client.get("/api/discovery/unmatched/999999")
    assert response.status_code == 404
```

Add `import json` to the test module if it is not already imported.

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest \
  tests/test_discovery_unmatched.py -k "every_spelling or declared_relation or missing_anime" -q
```

Expected: FAIL — the GET answers 405, because only POST routes exist under that path.

- [ ] **Step 3: Write the route**

In `backend/app/api/routes_discovery.py`, add the import:

```python
from app.providers.base import MANGA_FORMATS
```

and, beside the other `/discovery/unmatched` routes:

```python
# Where each provider publishes the anime the user is looking at. A media id on
# its own is not something anyone can check; a link is.
ANIME_URL = {
    "anilist": "https://anilist.co/anime/{media_id}",
    "mal": "https://myanimelist.net/anime/{media_id}",
}


@router.get("/discovery/unmatched/{anime_id}")
async def unmatched_detail(anime_id: int, session: Session) -> dict[str, Any]:
    """One anime, in full.

    The list payload deliberately carries only what a row renders - five
    hundred rows paged at fifty would otherwise carry five hundred relation
    lists - so everything the panel adds is fetched one anime at a time.
    """
    anime = await _load_anime(session, anime_id)

    related = await session.execute(
        text(
            """
            select provider, related_manga
              from anime_entry
             where id = any(:ids)
            """
        ),
        {"ids": [member.row_id for member in anime.members]},
    )
    declared: list[dict[str, Any]] = []
    for row in related.all():
        for item in row.related_manga or []:
            declared.append(
                {
                    "provider": item.get("provider") or row.provider,
                    "media_id": str(item.get("media_id") or ""),
                    "relation": item.get("relation"),
                    "title": item.get("title"),
                    "format": item.get("format"),
                    # The same set that keeps a light novel from being offered
                    # as a download. False here is the answer to "why is this
                    # anime on the unmatched screen at all".
                    "usable": item.get("format") in MANGA_FORMATS,
                }
            )

    return {
        **anime_payload(anime),
        "synonyms": list(anime.synonyms),
        "members": [
            {
                "provider": str(member.provider),
                "media_id": member.media_id,
                "url": ANIME_URL.get(str(member.provider), "").format(
                    media_id=member.media_id
                )
                or None,
            }
            for member in anime.members
        ],
        "related": declared,
    }
```

Check `_load_anime`: if it does not already raise a 404 for an unknown id, add that check here before using the result.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend
POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests -q
.venv/bin/python -m ruff check app/ tests/
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes_discovery.py backend/tests/test_discovery_unmatched.py
git commit -m "feat(api): serve one unmatched anime's spellings and declared relations

The list payload carries what a row renders and no more, because five hundred
rows paged at fifty would otherwise carry five hundred relation lists. A
relation marked unusable is the answer to why the anime is on that screen."
```

---

## Task 2: The shared detail panel shell

**Files:**
- Create: `frontend/src/ui/DetailPanel.tsx`
- Modify: `frontend/src/ui/index.ts`

**Interfaces:**
- Consumes: `Icon`, `IconButton` from `ui/`.
- Produces: `<DetailPanel title={string} onClose={() => void}>{children}</DetailPanel>`. Tasks 3 and 4 both render into it.

Two screens need this, so it lives in `ui/`. Below `lg` a sticky side column has nowhere to sit, so the same component renders as a bottom sheet over the list — one component, because a second one is how the two screens' panels drift apart.

- [ ] **Step 1: Write the shell**

Create `frontend/src/ui/DetailPanel.tsx`:

```tsx
import { useEffect, type ReactNode } from 'react'

import { Icon } from './Icon'

/**
 * The detail beside a list, on two screens.
 *
 * Above lg it is a sticky column that scrolls with the page and stops below
 * the header. Below lg there is no room for a column, so the same panel is a
 * sheet over the list - one component rather than two, because two is how the
 * unmatched panel and the discovery panel would quietly stop behaving alike.
 *
 * Escape closes it. A panel that can only be dismissed by hunting for a small
 * button is the thing that makes a two-pane list feel like a trap.
 */
export function DetailPanel({
  title,
  onClose,
  children,
}: {
  title: string
  onClose: () => void
  children: ReactNode
}) {
  useEffect(() => {
    const dismiss = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', dismiss)
    return () => window.removeEventListener('keydown', dismiss)
  }, [onClose])

  return (
    <aside
      aria-label={title}
      className="fixed inset-x-0 bottom-0 z-20 max-h-[75vh] overflow-y-auto rounded-t-xl bg-surface-container p-space-lg pb-nav-clearance shadow-overlay lg:static lg:z-0 lg:max-h-[calc(100vh-8rem)] lg:rounded-xl lg:pb-space-lg lg:shadow-card"
    >
      <div className="mb-space-md flex items-start justify-between gap-space-sm">
        <h2 className="min-w-0 text-headline-sm text-on-surface">{title}</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close details"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-outline transition-colors hover:bg-surface-container-high hover:text-on-surface"
        >
          <Icon name="chevron" className="h-4 w-4 -rotate-90" />
        </button>
      </div>
      <div className="flex flex-col gap-space-md">{children}</div>
    </aside>
  )
}
```

Add to `frontend/src/ui/index.ts` in alphabetical position:

```typescript
export { DetailPanel } from './DetailPanel'
```

- [ ] **Step 2: Verify the build and the classes**

```bash
cd frontend
npm run build
grep -r "pb-nav-clearance" dist/ | head -1
grep -r "shadow-overlay" dist/ | head -1
grep -r "max-h-\[75vh\]" dist/ | head -1
```

Expected: build succeeds and all three greps match. `pb-nav-clearance` exists because `nav-clearance` is a `spacing` token — it is the bottom navigation's height plus a gutter, and a sheet that ignores it sits behind the nav on a phone.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/ui/DetailPanel.tsx frontend/src/ui/index.ts
git commit -m "feat(web): add the detail panel shell two list screens share

A sticky column above lg and a sheet below it, in one component: two would be
how the unmatched panel and the discovery panel stop behaving alike."
```

---

## Task 3: The unmatched detail panel

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/features/unmatched/UnmatchedDetail.tsx`
- Modify: `frontend/src/features/unmatched/AnimeRow.tsx`
- Modify: `frontend/src/features/unmatched/UnmatchedPage.tsx`

**Interfaces:**
- Consumes: `GET /api/discovery/unmatched/{id}` from Task 1; `<DetailPanel>` from Task 2.
- Produces: `UnmatchedDetail` type, `api.unmatchedDetail(id)`, `<UnmatchedDetail anime={UnmatchedAnime} onClose={...} />`. Nothing consumes them.

- [ ] **Step 1: Add the type and the call**

In `frontend/src/lib/api.ts`:

```typescript
/** One relation a provider declared for an anime, and whether it points at
 * something the downloader could ever fetch. `usable: false` — a light novel,
 * typically — is the reason the anime is on the unmatched screen. */
export interface DeclaredRelation {
  provider: string
  media_id: string
  relation: string | null
  title: string | null
  format: string | null
  usable: boolean
}

export interface AnimeMember {
  provider: string
  media_id: string
  url: string | null
}

export interface UnmatchedDetail extends UnmatchedAnime {
  synonyms: string[]
  members: AnimeMember[]
  related: DeclaredRelation[]
}
```

and to the `api` object:

```typescript
  unmatchedDetail: (id: number) =>
    request<UnmatchedDetail>(`/api/discovery/unmatched/${id}`),
```

- [ ] **Step 2: Write the panel body**

Create `frontend/src/features/unmatched/UnmatchedDetail.tsx`:

```tsx
import { useCallback } from 'react'

import { Badge, DetailPanel, ErrorState, Skeleton } from '../../ui'
import { api, type UnmatchedAnime } from '../../lib/api'
import { PROVIDER_LABEL } from '../../lib/format'
import { useAsyncData } from '../../lib/useAsyncData'
import { STATUS_LABEL } from './labels'

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-space-sm">
      <span className="font-mono text-label-sm text-outline">{label}</span>
      <span className="font-mono text-label-md text-on-surface">{value}</span>
    </div>
  )
}

export function UnmatchedDetail({
  anime,
  onClose,
}: {
  anime: UnmatchedAnime
  onClose: () => void
}) {
  const load = useCallback(() => api.unmatchedDetail(anime.id), [anime.id])
  const { data, error, reload } = useAsyncData(load)

  return (
    <DetailPanel title={anime.title ?? anime.title_romaji ?? 'Untitled'} onClose={onClose}>
      <div className="aspect-[2/3] w-32 overflow-hidden rounded-lg bg-surface-container-highest">
        {anime.cover_url && (
          <img src={anime.cover_url} alt="" className="h-full w-full object-cover" />
        )}
      </div>

      {/* The row already carried these, so they render before the request
          lands rather than sitting behind a skeleton the user does not need. */}
      <div className="flex flex-col gap-space-xs">
        {anime.title_romaji && <Row label="Romaji" value={anime.title_romaji} />}
        {anime.title_english && <Row label="English" value={anime.title_english} />}
        <Row label="Status" value={STATUS_LABEL[anime.status] ?? anime.status} />
        <Row
          label="Episodes"
          value={
            anime.total_episodes != null
              ? `${anime.progress_episode} of ${anime.total_episodes}`
              : `${anime.progress_episode} watched`
          }
        />
      </div>

      {!data && error ? (
        <ErrorState title="Couldn't load the details" detail={error} onRetry={reload} />
      ) : !data ? (
        <div className="flex flex-col gap-space-sm">
          <Skeleton className="h-6 w-32" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : (
        <>
          {data.synonyms.length > 0 && (
            <section className="flex flex-col gap-space-xs">
              <h3 className="font-mono text-label-sm uppercase tracking-wide text-outline">
                Also known as
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {data.synonyms.map((name) => (
                  <span
                    key={name}
                    className="rounded bg-surface-container-high px-2 py-0.5 font-mono text-label-sm text-on-surface-variant"
                  >
                    {name}
                  </span>
                ))}
              </div>
              {/* Every one of these is searched, which is why a filter that
                  matches none of the two titles can still find this anime. */}
              <p className="text-body-sm text-outline">
                Every spelling is searched, not just the two titles above.
              </p>
            </section>
          )}

          <section className="flex flex-col gap-space-xs">
            <h3 className="font-mono text-label-sm uppercase tracking-wide text-outline">
              On your lists
            </h3>
            {data.members.map((member) => (
              <div
                key={`${member.provider}:${member.media_id}`}
                className="flex items-center justify-between gap-space-sm"
              >
                <span className="text-body-sm text-on-surface">
                  {PROVIDER_LABEL[member.provider] ?? member.provider}
                </span>
                {member.url ? (
                  <a
                    href={member.url}
                    target="_blank"
                    rel="noreferrer"
                    className="font-mono text-label-sm text-primary hover:underline"
                  >
                    #{member.media_id}
                  </a>
                ) : (
                  <span className="font-mono text-label-sm text-outline">
                    #{member.media_id}
                  </span>
                )}
              </div>
            ))}
          </section>

          <section className="flex flex-col gap-space-xs">
            <h3 className="font-mono text-label-sm uppercase tracking-wide text-outline">
              Declared relations
            </h3>
            {data.related.length === 0 ? (
              // Not an error, and not an empty list to shrug at: this is the
              // answer to why the anime is on this screen.
              <p className="text-body-sm text-on-surface-variant">
                Neither provider declared a manga for this anime. Searching by name is
                the only way to find one.
              </p>
            ) : (
              data.related.map((relation) => (
                <div
                  key={`${relation.provider}:${relation.media_id}`}
                  className="flex flex-col gap-0.5 rounded-lg bg-surface-container-low p-space-sm"
                >
                  <div className="flex items-center justify-between gap-space-sm">
                    <span className="min-w-0 truncate text-body-sm text-on-surface">
                      {relation.title ?? `#${relation.media_id}`}
                    </span>
                    {relation.usable ? (
                      <Badge tone="secondary">Usable</Badge>
                    ) : (
                      <Badge tone="warning">Not a manga</Badge>
                    )}
                  </div>
                  <span className="font-mono text-label-sm text-outline">
                    {[relation.relation, relation.format].filter(Boolean).join(' · ')}
                  </span>
                </div>
              ))
            )}
          </section>
        </>
      )}
    </DetailPanel>
  )
}
```

Check `features/unmatched/labels.ts` for the exported name of the status map before importing `STATUS_LABEL` — use whatever it actually exports.

- [ ] **Step 3: Make rows selectable**

In `frontend/src/features/unmatched/AnimeRow.tsx`, add two props and wire them:

```tsx
  selected,
  onSelect,
```

typed as `selected: boolean` and `onSelect: () => void`. Put the selection affordance on the row's outer element:

```tsx
    className={`... ${selected ? 'ring-1 ring-primary' : ''}`}
```

and give the row's title a button that calls `onSelect`. Do **not** make the whole row a click target: the row already carries Search, Hide and Add controls, and swallowing clicks on those is the bug this avoids.

- [ ] **Step 4: Wire the page**

In `frontend/src/features/unmatched/UnmatchedPage.tsx`, add:

```tsx
const [selected, setSelected] = useState<UnmatchedAnime | null>(null)
```

Wrap the list and the panel in a two-column grid that collapses to one:

```tsx
<div className={selected ? 'grid grid-cols-1 gap-space-lg lg:grid-cols-[1fr_360px]' : ''}>
  <div className="flex min-w-0 flex-col gap-space-md">{/* the existing list */}</div>
  {selected && <UnmatchedDetail anime={selected} onClose={() => setSelected(null)} />}
</div>
```

Pass `selected={selected?.id === anime.id}` and `onSelect={() => setSelected(anime)}` to each `AnimeRow`. Clear the selection whenever the page, the filter or the hidden/open view changes — a panel describing a row that is no longer on screen is worse than no panel:

```tsx
useEffect(() => {
  setSelected(null)
}, [offset, filter, showHidden])
```

- [ ] **Step 5: Verify**

```bash
cd frontend
npm run build
grep -r "ring-primary" dist/ | head -1
grep -r "lg:grid-cols-\[1fr_360px\]" dist/ | head -1
```

Then in the running stack: open `/unmatched`, select a row, confirm the panel opens beside the list, that Search/Hide/Add on that row still work, that Escape closes it, and that paging clears it. At a phone width, confirm the panel is a sheet that does not sit behind the bottom navigation.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/features/unmatched/UnmatchedDetail.tsx \
        frontend/src/features/unmatched/AnimeRow.tsx \
        frontend/src/features/unmatched/UnmatchedPage.tsx
git commit -m "feat(web): show an unmatched anime's details beside the list

Selection sits on the title rather than the whole row: the row already carries
Search, Hide and Add, and a row-wide click target swallows all three.

The panel names every spelling that gets searched and every relation that was
declared, which is the answer to why the anime is on that screen at all."
```

---

## Task 4: The discovery detail panel

**Files:**
- Create: `frontend/src/features/discovery/SuggestionDetail.tsx`
- Modify: `frontend/src/features/discovery/SuggestionCard.tsx`
- Modify: `frontend/src/features/discovery/DiscoveryPage.tsx`

**Interfaces:**
- Consumes: `Suggestion` (already typed in `lib/api.ts`) and `<DetailPanel>` from Task 2.
- Produces: `<SuggestionDetail suggestion={Suggestion} onClose={...} />`. Nothing consumes it.

No request is made here. `GET /api/suggestions` already serves `sources`, `best_source`, `reason` and `write_results` for every suggestion, and the card renders a fraction of it — the panel is the rest of what the screen already has in hand.

- [ ] **Step 1: Write the panel body**

Create `frontend/src/features/discovery/SuggestionDetail.tsx`:

```tsx
import { Badge, DetailPanel } from '../../ui'
import type { Suggestion } from '../../lib/api'
import { PROVIDER_LABEL, relativeTime } from '../../lib/format'

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-space-sm">
      <span className="font-mono text-label-sm text-outline">{label}</span>
      <span className="font-mono text-label-md text-on-surface">{value}</span>
    </div>
  )
}

export function SuggestionDetail({
  suggestion,
  onClose,
}: {
  suggestion: Suggestion
  onClose: () => void
}) {
  const { reason, sources, best_source: best, write_results: writes } = suggestion

  return (
    <DetailPanel title={suggestion.title} onClose={onClose}>
      <div className="aspect-[2/3] w-32 overflow-hidden rounded-lg bg-surface-container-highest">
        {suggestion.cover_url && (
          <img src={suggestion.cover_url} alt="" className="h-full w-full object-cover" />
        )}
      </div>

      <div className="flex flex-col gap-space-xs">
        {suggestion.year != null && <Row label="Year" value={`${suggestion.year}`} />}
        {suggestion.total_chapters != null && (
          <Row label="Chapters" value={`${suggestion.total_chapters}`} />
        )}
        {suggestion.publishing_status && (
          <Row label="Publication" value={suggestion.publishing_status} />
        )}
        {/* The rank is how the list is ordered, so the screen owes the user the
            number it ordered by rather than only the position. */}
        <Row label="Rank score" value={suggestion.rank_score.toFixed(3)} />
      </div>

      <section className="flex flex-col gap-space-xs">
        <h3 className="font-mono text-label-sm uppercase tracking-wide text-outline">
          Why this is here
        </h3>
        {reason.origin_title ? (
          <p className="text-body-md text-on-surface-variant">
            Your anime{' '}
            <span className="font-semibold text-on-surface">{reason.origin_title}</span>
            {reason.relation && <> is linked to it as {reason.relation.toLowerCase()}</>}
            {reason.total_episodes != null && <> across {reason.total_episodes} episodes</>}.
          </p>
        ) : (
          <p className="text-body-sm text-outline">
            No origin anime was recorded for this suggestion.
          </p>
        )}
      </section>

      <section className="flex flex-col gap-space-xs">
        <h3 className="font-mono text-label-sm uppercase tracking-wide text-outline">
          Sources found
        </h3>
        {sources.length === 0 ? (
          <p className="text-body-sm text-on-surface-variant">
            No source site matched this title. Adding it will park it for review rather
            than downloading anything.
          </p>
        ) : (
          sources.map((source) => (
            <div
              key={source.url}
              className="flex items-center justify-between gap-space-sm rounded-lg bg-surface-container-low px-space-sm py-space-xs"
            >
              <div className="flex min-w-0 flex-col">
                <span className="text-body-sm text-on-surface">{source.site}</span>
                <span className="truncate font-mono text-label-sm text-outline">
                  {source.chapters != null ? `${source.chapters} chapters` : 'chapter count unknown'}
                </span>
              </div>
              <div className="flex shrink-0 items-center gap-space-xs">
                {best?.url === source.url && <Badge tone="secondary">Best</Badge>}
                <span className="font-mono text-label-sm text-outline">
                  {source.score.toFixed(2)}
                </span>
              </div>
            </div>
          ))
        )}
      </section>

      {writes.length > 0 && (
        <section className="flex flex-col gap-space-xs">
          <h3 className="font-mono text-label-sm uppercase tracking-wide text-outline">
            Written to
          </h3>
          {writes.map((write) => (
            <div key={write.target} className="flex flex-col gap-0.5">
              <div className="flex items-center justify-between gap-space-sm">
                <span className="text-body-sm text-on-surface">
                  {PROVIDER_LABEL[write.target] ?? write.target}
                </span>
                {/* Skipped is an absence, not a failure: MangaDex with no
                    personal credentials is the default setup and has nothing
                    to say to the user. */}
                {write.skipped ? (
                  <Badge tone="tertiary">Not configured</Badge>
                ) : write.ok ? (
                  <Badge tone="secondary">Written</Badge>
                ) : (
                  <Badge tone="error">Failed</Badge>
                )}
              </div>
              {write.error && (
                <span className="text-body-sm text-error">{write.error}</span>
              )}
              {write.at && (
                <span className="font-mono text-label-sm text-outline">
                  {relativeTime(write.at)}
                </span>
              )}
            </div>
          ))}
        </section>
      )}
    </DetailPanel>
  )
}
```

- [ ] **Step 2: Make cards selectable**

In `frontend/src/features/discovery/SuggestionCard.tsx`, add `selected: boolean` and `onSelect: () => void`, mark the selected card with `ring-1 ring-primary` on its outer element, and put the click target on the cover and the title — not on the card, which already carries the add-and-dismiss controls.

- [ ] **Step 3: Wire the page**

In `frontend/src/features/discovery/DiscoveryPage.tsx`, mirror Task 3: a `selected` state, the same two-column grid, `selected`/`onSelect` on each card, and a reset when the state filter changes.

The selected suggestion must be re-read from the list on every render rather than stored whole, or approving it leaves the panel showing the state it had before the approval:

```tsx
const [selectedId, setSelectedId] = useState<number | null>(null)
const selected = suggestions.find((item) => item.id === selectedId) ?? null
```

- [ ] **Step 4: Verify**

```bash
cd frontend
npm run build
grep -r "ring-primary" dist/ | head -1
```

Then in the running stack: open `/discovery`, select a card, confirm the panel shows the reason chain, every source with its score and the best one marked, and the per-target write results. Approve the selected suggestion and confirm the panel follows the change rather than going stale. Confirm Escape closes it, and that the sheet at phone width clears the bottom navigation.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/discovery/SuggestionDetail.tsx \
        frontend/src/features/discovery/SuggestionCard.tsx \
        frontend/src/features/discovery/DiscoveryPage.tsx
git commit -m "feat(web): show a suggestion's sources and write results beside the list

No new request: /api/suggestions already serves the reason chain, every source
with its score and the per-target write results, and the card rendered a
fraction of it. The panel reads the selection out of the list each render, so
approving one does not leave it showing the state it had before."
```

---

## Self-review

**Spec coverage.** The maintainer's request was a detail view on Unmatched and Discovery, matching the library's behaviour, as a side panel. Task 2 builds the shell, Task 3 the unmatched body and its backend, Task 4 the discovery body. Nothing in the request is unimplemented.

**Placeholders.** Two steps deliberately describe an edit rather than restate a whole file — Task 3's Step 3 (`AnimeRow` props) and Task 4's Step 2 (`SuggestionCard` props). Both name the exact props, their types, the class to add and where the click target must and must not go. Both files are short enough to hold in view while editing.

**Type consistency.** `UnmatchedDetail` extends `UnmatchedAnime`, so the panel renders the row's fields before its own request lands and the two can never disagree about a field's name. `DeclaredRelation.usable` is produced by Task 1 and consumed by Task 3 under that name. `DetailPanel`'s `{title, onClose, children}` signature is used identically by both bodies.

**One judgement worth naming.** The discovery panel makes no request because the list payload already holds everything it shows. If a later change trims that payload for the sake of the card, this panel goes blank without a type error to warn anyone — the list route's own docstring is where that should be noted if the payload is ever narrowed.
