# Web Redesign — Foundation and Existing Screens Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hand-styled four-page interface with the design system from `.redesign/`, and extend the API so the redesigned screens are driven by real data rather than placeholders.

**Architecture:** A Tailwind token layer generated from `DESIGN.md` front matter is the single source for every colour, size and space. Above it sit presentational primitives in `ui/`, one folder per screen in `features/`, and an `AppShell` that owns navigation and live status. On the backend, two additions: reading status and progress exposed on the series list, and a `PROGRESS_WRITE` job that pushes an explicit chapter number forward-only.

**Tech Stack:** React 18, TypeScript, Vite, Tailwind CSS 3 with PostCSS, `@fontsource`, React Router 6, FastAPI, SQLAlchemy 2 async, Postgres 17, Alembic, pytest.

**Spec:** `docs/superpowers/specs/2026-09-13-web-redesign-design.md`

## Global Constraints

- Every string in the interface is English. The mockups are Portuguese; translate, never transcribe.
- **Each screen is built to match its reference render.** Every folder in `.redesign/` holds a `screen.png` rendered from its own `code.html`; that image is the acceptance target, not a suggestion. Verification for a screen means screenshotting the built page at the reference's width, comparing section by section against the render, and iterating until the two read as the same screen. The comparison goes in the report, section by section. Three things still outrank the picture: every string is English, no element is kept alive by an invented number, and `DESIGN.md`'s responsive section governs the narrow widths the desktop renders say nothing about. `DESIGN.md`'s Components section carries the numbers the image only implies — hover lift, track height, badge tint opacity — and those come from the document rather than from eyeballing the pixels.
- No hex colour, font size, radius or spacing value appears outside `frontend/tailwind.config.ts`.
- Fonts and icons are bundled. No `fonts.googleapis.com`, no `cdn.tailwindcss.com`, no Material Symbols stylesheet. The interface must render completely with no outbound route.
- The token map comes from the **front matter** of `.redesign/obsidian_vault/DESIGN.md`, not its prose. Where they disagree, front matter wins — it is what the mockups embed.
- Feature folders never import from each other. Anything two features need lives in `ui/`.
- No screen ships a widget whose number is invented. If the API cannot serve it, leave it out.
- A progress write that would move a provider backwards is never sent.
- Commits: imperative, scoped subject (`feat(web):`, `feat(api):`, `chore:`). Body says why. No trailers of any kind, no tool attribution.
- Alembic is not on PATH. Invoke it as `python -m alembic`, including from subprocesses in tests.
- Backend tests need a throwaway Postgres. Prefix commands with `POSTGRES_HOST=localhost POSTGRES_PORT=5434`, not the `5433` that `CLAUDE.md` documents. The container on 5433 is shared with other worktrees and has been migrated past this branch's Alembic chain by the discovery branch; a database whose schema is ahead of the branch under test makes the tests lie about the branch. The isolated container is `manga-pg-web-redesign`.

## File Structure

**Created:**

| Path | Responsibility |
|---|---|
| `frontend/tailwind.config.ts` | The token map. Single source for colour, type, radius, spacing. |
| `frontend/postcss.config.js` | Tailwind + autoprefixer pipeline. |
| `frontend/src/styles/index.css` | Tailwind layers, font faces, the two or three base rules. |
| `frontend/src/ui/*.tsx` | Presentational primitives. One component per file. |
| `frontend/src/app/AppShell.tsx` | Header, navigation, status strip, outlet. |
| `frontend/src/app/routes.tsx` | Route table. |
| `frontend/src/features/<screen>/` | One folder per screen. |
| `frontend/src/lib/format.ts` | Chapter numbers, relative times, byte sizes. |
| `backend/app/api/routes_health.py` | `GET /api/health/integrations`. |
| `backend/app/handlers/progress_write.py` | `PROGRESS_WRITE` handler. |
| `backend/tests/test_progress_write.py` | Forward-only guard. |

**Modified:**

| Path | Change |
|---|---|
| `frontend/package.json` | Tailwind, PostCSS, autoprefixer, `@fontsource` packages. |
| `frontend/src/main.tsx` | Import `styles/index.css` instead of `styles.css`. |
| `frontend/src/App.tsx` | Reduced to composing `AppShell` and `routes`. |
| `frontend/src/api.ts` | Moves to `lib/api.ts`; new types and calls. |
| `frontend/src/useEvents.ts` | Moves to `lib/useEvents.ts`. |
| `backend/app/enums.py` | `JobType.PROGRESS_WRITE`. |
| `backend/app/api/routes_series.py` | `LIST_SQL` extension, detail route, progress route. |
| `backend/app/api/main.py` | Register the health router. |
| `backend/app/settings_store.py` | Four new keys. |

**Deleted:** `frontend/src/styles.css` at the end of Task 4, once nothing imports it.

---

### Task 1: The token layer

Closes #6.

**Files:**
- Create: `frontend/tailwind.config.ts`, `frontend/postcss.config.js`, `frontend/src/styles/index.css`, `frontend/src/ui/Icon.tsx`
- Modify: `frontend/package.json`, `frontend/src/main.tsx`
- Test: build only — see Step 5

**Interfaces:**
- Consumes: nothing.
- Produces: the Tailwind class vocabulary every later task uses — `bg-surface-container`, `text-on-surface-variant`, `font-label-sm`, `rounded-lg`, `p-gutter`, `gap-space-md`, and the semantic status names below. Plus `<Icon name="sync" className="..." />`, where `name` is a key of the `ICONS` record.

- [ ] **Step 1: Install the dependencies**

```bash
cd frontend
npm install -D tailwindcss@^3.4.17 postcss@^8.4.49 autoprefixer@^10.4.20
npm install @fontsource/plus-jakarta-sans@^5.1.0 @fontsource/jetbrains-mono@^5.1.1
```

- [ ] **Step 2: Write the token config**

The colour values are transcribed from the front matter of `.redesign/obsidian_vault/DESIGN.md`. `warning` is the single addition, because five reading statuses do not fit four Material 3 roles without overloading one.

Create `frontend/tailwind.config.ts`:

```ts
import type { Config } from 'tailwindcss'

/**
 * The token map from .redesign/obsidian_vault/DESIGN.md front matter.
 *
 * That file also carries a prose palette naming #8b5cf6 over #0d1117. It
 * disagrees with this map and loses: every mockup in .redesign/ embeds these
 * values, and the screenshots were rendered from them.
 */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: '#10141a',
        'on-background': '#dfe2eb',
        surface: '#10141a',
        'surface-dim': '#10141a',
        'surface-bright': '#353940',
        'surface-container-lowest': '#0a0e14',
        'surface-container-low': '#181c22',
        'surface-container': '#1c2026',
        'surface-container-high': '#262a31',
        'surface-container-highest': '#31353c',
        'surface-variant': '#31353c',
        'on-surface': '#dfe2eb',
        'on-surface-variant': '#cbc3d7',
        'inverse-surface': '#dfe2eb',
        'inverse-on-surface': '#2d3137',
        outline: '#958ea0',
        'outline-variant': '#494454',
        primary: '#d0bcff',
        'on-primary': '#3c0091',
        'primary-container': '#a078ff',
        'on-primary-container': '#340080',
        'inverse-primary': '#6d3bd7',
        secondary: '#4edea3',
        'on-secondary': '#003824',
        'secondary-container': '#00a572',
        'on-secondary-container': '#00311f',
        tertiary: '#7bd0ff',
        'on-tertiary': '#00354a',
        'tertiary-container': '#009bd1',
        'on-tertiary-container': '#002d40',
        error: '#ffb4ab',
        'on-error': '#690005',
        'error-container': '#93000a',
        'on-error-container': '#ffdad6',
        // Not in the source map. A fifth reading status needs a fifth role.
        warning: '#ffb877',
        'on-warning': '#4a2600',
        'warning-container': '#c2691a',
        'on-warning-container': '#3a1d00',
      },
      fontFamily: {
        sans: ['Plus Jakarta Sans', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        'display-lg': ['3rem', { lineHeight: '3.5rem', letterSpacing: '-0.03em', fontWeight: '800' }],
        'display-sm': ['2.25rem', { lineHeight: '2.75rem', letterSpacing: '-0.02em', fontWeight: '700' }],
        'headline-lg': ['1.75rem', { lineHeight: '2.25rem', letterSpacing: '-0.02em', fontWeight: '700' }],
        'headline-md': ['1.375rem', { lineHeight: '1.875rem', letterSpacing: '-0.01em', fontWeight: '600' }],
        'headline-sm': ['1.125rem', { lineHeight: '1.5rem', fontWeight: '600' }],
        'title-md': ['1rem', { lineHeight: '1.375rem', fontWeight: '600' }],
        'body-lg': ['1rem', { lineHeight: '1.625rem', fontWeight: '400' }],
        'body-md': ['0.875rem', { lineHeight: '1.375rem', fontWeight: '400' }],
        'body-sm': ['0.75rem', { lineHeight: '1.125rem', fontWeight: '400' }],
        'label-md': ['0.8125rem', { lineHeight: '1.125rem', letterSpacing: '0.02em', fontWeight: '500' }],
        'label-sm': ['0.6875rem', { lineHeight: '0.9375rem', letterSpacing: '0.04em', fontWeight: '600' }],
      },
      borderRadius: {
        sm: '0.25rem',
        DEFAULT: '0.5rem',
        md: '0.75rem',
        lg: '1rem',
        xl: '1.5rem',
        full: '9999px',
      },
      spacing: {
        gutter: '1.25rem',
        margin: '2rem',
        'space-xs': '0.25rem',
        'space-sm': '0.5rem',
        'space-md': '1rem',
        'space-lg': '1.5rem',
        'space-xl': '2.5rem',
      },
      maxWidth: { canvas: '1440px' },
      boxShadow: {
        card: '0 8px 24px -4px rgba(0, 0, 0, 0.45)',
        overlay: '0 20px 40px -12px rgba(208, 188, 255, 0.12)',
        glow: '0 8px 20px -2px rgba(208, 188, 255, 0.25)',
      },
    },
  },
  plugins: [],
} satisfies Config
```

- [ ] **Step 3: Write the PostCSS config and the stylesheet**

Create `frontend/postcss.config.js`:

```js
export default {
  plugins: { tailwindcss: {}, autoprefixer: {} },
}
```

Create `frontend/src/styles/index.css`. The font imports are package imports, not network requests — that is the point of `@fontsource`.

```css
@import '@fontsource/plus-jakarta-sans/400.css';
@import '@fontsource/plus-jakarta-sans/500.css';
@import '@fontsource/plus-jakarta-sans/600.css';
@import '@fontsource/plus-jakarta-sans/700.css';
@import '@fontsource/plus-jakarta-sans/800.css';
@import '@fontsource/jetbrains-mono/400.css';
@import '@fontsource/jetbrains-mono/500.css';
@import '@fontsource/jetbrains-mono/600.css';

@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  html {
    color-scheme: dark;
  }
  body {
    @apply bg-background font-sans text-body-md text-on-surface antialiased;
    margin: 0;
    overscroll-behavior: none;
  }
}
```

- [ ] **Step 4: Write the icon component**

The mockups load Material Symbols from a stylesheet. Replace it with inline paths so the interface keeps its icons offline. Start with the set the shell and library need; later tasks add keys to the same record.

Create `frontend/src/ui/Icon.tsx`:

```tsx
const ICONS = {
  sync: 'M12 4V1L8 5l4 4V6a6 6 0 1 1-6 6H4a8 8 0 1 0 8-8z',
  add: 'M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6z',
  check: 'M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z',
  grid: 'M3 3h8v8H3zm10 0h8v8h-8zM3 13h8v8H3zm10 0h8v8h-8z',
  list: 'M3 5h18v2H3zm0 6h18v2H3zm0 6h18v2H3z',
  search: 'M15.5 14h-.8l-.3-.3a6.5 6.5 0 1 0-.7.7l.3.3v.8l5 5 1.5-1.5zm-6 0a4.5 4.5 0 1 1 0-9 4.5 4.5 0 0 1 0 9z',
  book: 'M18 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2zm0 18H6V4h12z',
  download: 'M12 16 7 11l1.4-1.4L11 12.2V4h2v8.2l2.6-2.6L17 11zM5 18h14v2H5z',
  settings: 'M12 15.5A3.5 3.5 0 1 1 15.5 12 3.5 3.5 0 0 1 12 15.5zm7.4-2.3.1-1.2-.1-1.2 2-1.5-2-3.4-2.3 1a7.6 7.6 0 0 0-2-1.2l-.4-2.4h-4l-.4 2.4a7.6 7.6 0 0 0-2 1.2l-2.3-1-2 3.4 2 1.5-.1 1.2.1 1.2-2 1.5 2 3.4 2.3-1a7.6 7.6 0 0 0 2 1.2l.4 2.4h4l.4-2.4a7.6 7.6 0 0 0 2-1.2l2.3 1 2-3.4z',
  sparkle: 'M12 2l2.4 6.6L21 11l-6.6 2.4L12 20l-2.4-6.6L3 11l6.6-2.4z',
  chart: 'M4 20V10h4v10zm6 0V4h4v16zm6 0v-6h4v6z',
  warning: 'M1 21h22L12 2zm12-3h-2v-2h2zm0-4h-2v-4h2z',
} as const

export type IconName = keyof typeof ICONS

export function Icon({ name, className = 'h-4 w-4' }: { name: IconName; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden className={className}>
      <path d={ICONS[name]} />
    </svg>
  )
}
```

- [ ] **Step 5: Point the entry at the new stylesheet and verify the build**

In `frontend/src/main.tsx`, replace `import './styles.css'` with `import './styles/index.css'`.

Run:

```bash
cd frontend && npm run build
```

Expected: PASS. `tsc -b` clean, Vite emits a bundle.

- [ ] **Step 6: Verify nothing reaches the network**

Run:

```bash
cd frontend && grep -rn "googleapis\|gstatic\|cdn.tailwindcss" src/ index.html || echo "no external references"
```

Expected: `no external references`.

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/tailwind.config.ts \
        frontend/postcss.config.js frontend/src/styles/index.css frontend/src/ui/Icon.tsx \
        frontend/src/main.tsx
git commit -m "feat(web): adopt the design token system

Colours, type and spacing were literals spread across a stylesheet, so
restyling meant hunting for hexes. Fonts and icons are bundled rather than
fetched: this runs on a homelab box that may have no route out, and an
interface that loses its typography when the WAN drops is not self-hosted."
```

---

### Task 2: Integration health endpoint

Closes part of #7. Split from the shell because it has a test cycle of its own and a reviewer could reject it independently.

**Files:**
- Create: `backend/app/api/routes_health.py`
- Modify: `backend/app/api/main.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `GET /api/health/integrations` returning `{"integrations": [{"name": str, "state": "ok" | "unauthenticated" | "unreachable", "detail": str | None}]}`, with `name` in `mal`, `anilist`, `mangadex`, `komga`, `comick`. The shell renders this; the settings screen reuses it.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_api.py`:

```python
async def test_integration_health_reports_every_service(client):
    body = (await client.get("/api/health/integrations")).json()
    names = {item["name"] for item in body["integrations"]}
    assert names == {"mal", "anilist", "mangadex", "komga", "comick"}


async def test_integration_health_reports_unauthenticated_without_tokens(client):
    body = (await client.get("/api/health/integrations")).json()
    states = {item["name"]: item["state"] for item in body["integrations"]}
    assert states["mal"] == "unauthenticated"
    assert states["anilist"] == "unauthenticated"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend && POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest \
  tests/test_api.py -k integration_health -q
```

Expected: FAIL, 404 from an unregistered route.

- [ ] **Step 3: Write the router**

Create `backend/app/api/routes_health.py`:

```python
"""What the header strip reports.

Reachability and authentication are different failures with different fixes, so
they are different states. A strip that shows one dot for both sends the user to
the wrong settings section.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.enums import Provider
from app.komga import from_settings
from app.settings_store import get_setting

router = APIRouter(prefix="/api/health", tags=["health"])

Session = Annotated[AsyncSession, Depends(db_session)]


async def _token_providers(session: AsyncSession) -> set[str]:
    result = await session.execute(text("select provider from provider_token"))
    return {row.provider for row in result.all()}


def _entry(name: str, state: str, detail: str | None = None) -> dict[str, Any]:
    return {"name": name, "state": state, "detail": detail}


@router.get("/integrations")
async def integrations(session: Session) -> dict[str, Any]:
    authenticated = await _token_providers(session)
    items = [
        _entry(
            provider.value,
            "ok" if provider.value in authenticated else "unauthenticated",
        )
        for provider in (Provider.MAL, Provider.ANILIST)
    ]

    items.append(
        _entry("mangadex", "ok" if "mangadex" in authenticated else "unauthenticated")
    )

    komga = from_settings()
    items.append(
        _entry("komga", "ok" if komga.has_credentials else "unauthenticated")
    )

    comick_url = await get_setting(session, "comick_url")
    items.append(
        _entry("comick", "ok" if comick_url else "unauthenticated", comick_url or None)
    )

    return {"integrations": items}
```

If `get_setting` does not exist with that signature in `app/settings_store.py`, read the module and use whatever accessor it exposes; do not add a second one.

- [ ] **Step 4: Register the router**

In `backend/app/api/main.py`, import `routes_health` alongside the existing routers and add `app.include_router(routes_health.router)` next to them.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd backend && POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest \
  tests/test_api.py -k integration_health -q
```

Expected: PASS, 2 tests.

- [ ] **Step 6: Lint and commit**

```bash
cd backend && .venv/bin/python -m ruff check app/ tests/
git add backend/app/api/routes_health.py backend/app/api/main.py backend/tests/test_api.py
git commit -m "feat(api): report integration health for the header strip

Unreachable and unauthenticated are different failures with different fixes.
One dot covering both sends the user to the wrong settings section."
```

---

### Task 3: Application shell and primitives

Closes #7.

**Files:**
- Create: `frontend/src/ui/{Button,IconButton,Badge,StatusPill,Chip,Card,Toggle,SegmentedControl,ProgressBar,Skeleton,EmptyState}.tsx`, `frontend/src/ui/index.ts`, `frontend/src/app/AppShell.tsx`, `frontend/src/app/routes.tsx`, `frontend/src/lib/format.ts`
- Modify: `frontend/src/App.tsx`, move `frontend/src/api.ts` to `frontend/src/lib/api.ts`, move `frontend/src/useEvents.ts` to `frontend/src/lib/useEvents.ts`
- Test: build and browser — see Steps 5 and 6

**Interfaces:**
- Consumes: Task 1's Tailwind vocabulary and `Icon`; Task 2's `GET /api/health/integrations`.
- Produces:
  - `<AppShell />` rendering header plus `<Outlet />`.
  - `<Button variant="primary" | "surface" | "ghost" size="sm" | "md" icon?={IconName}>`
  - `<Badge tone="primary" | "secondary" | "tertiary" | "warning" | "error">`
  - `<StatusPill status={ListStatus} />` where `ListStatus` is `'reading' | 'plan_to_read' | 'completed' | 'on_hold' | 'dropped'`
  - `<Chip active count?={number} onClick>`
  - `<Card as?={'div' | 'section'} elevated?={boolean}>`
  - `<Toggle checked onChange label>`
  - `<SegmentedControl options={{value, icon?, label}[]} value onChange>`
  - `<ProgressBar value max tone?>`
  - `<Skeleton />`, `<EmptyState icon title detail action?>`
  - `formatChapter(n: number): string`, `relativeTime(iso: string): string`, `formatBytes(n: number): string`

- [ ] **Step 1: Write the status mapping and formatters**

The status-to-role mapping is the one piece of the design system with meaning rather than markup, so it lives in code exactly once.

Create `frontend/src/lib/format.ts`:

```ts
export type ListStatus = 'reading' | 'plan_to_read' | 'completed' | 'on_hold' | 'dropped'

export const STATUS_TONE: Record<ListStatus, 'secondary' | 'primary' | 'tertiary' | 'warning' | 'error'> = {
  reading: 'secondary',
  completed: 'primary',
  plan_to_read: 'tertiary',
  on_hold: 'warning',
  dropped: 'error',
}

export const STATUS_LABEL: Record<ListStatus, string> = {
  reading: 'Reading',
  plan_to_read: 'Plan to read',
  completed: 'Completed',
  on_hold: 'On hold',
  dropped: 'Dropped',
}

/** Chapter numbers are decimals. 12.00 reads as 12; 12.50 must stay 12.5. */
export function formatChapter(value: number): string {
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(2)))
}

export function relativeTime(iso: string): string {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000)
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ['second', 60], ['minute', 60], ['hour', 24], ['day', 7], ['week', 4.35], ['month', 12],
  ]
  let value = seconds
  for (const [unit, step] of units) {
    if (Math.abs(value) < step) {
      return new Intl.RelativeTimeFormat('en', { numeric: 'auto' }).format(-Math.round(value), unit)
    }
    value /= step
  }
  return new Intl.RelativeTimeFormat('en', { numeric: 'auto' }).format(-Math.round(value), 'year')
}

export function formatBytes(bytes: number): string {
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value.toFixed(value >= 100 || unit === 0 ? 0 : 2)} ${units[unit]}`
}
```

- [ ] **Step 2: Write the primitives**

Each file exports one component, takes its data as props, holds no state beyond presentation, and composes Tailwind token classes only. Two carry decisions worth stating in the file:

`frontend/src/ui/StatusPill.tsx` — reads `STATUS_TONE` and `STATUS_LABEL` from `lib/format.ts` rather than repeating the mapping. Renders a pill: a 6 px dot, a `font-mono text-label-sm` label, a 12%-alpha tint behind solid foreground text, per the component spec in `DESIGN.md`.

```tsx
import { STATUS_LABEL, STATUS_TONE, type ListStatus } from '../lib/format'

const TINT: Record<string, string> = {
  secondary: 'bg-secondary/10 text-secondary',
  primary: 'bg-primary/10 text-primary',
  tertiary: 'bg-tertiary/10 text-tertiary',
  warning: 'bg-warning/10 text-warning',
  error: 'bg-error/10 text-error',
}

export function StatusPill({ status }: { status: ListStatus }) {
  const tone = STATUS_TONE[status]
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-space-sm py-0.5 font-mono text-label-sm ${TINT[tone]}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {STATUS_LABEL[status]}
    </span>
  )
}
```

`frontend/src/ui/ProgressBar.tsx` — clamps rather than trusting its inputs, because a provider that reports progress past a stale total would otherwise paint outside its track.

```tsx
type Tone = 'primary' | 'secondary' | 'tertiary' | 'warning' | 'error'

/**
 * Tailwind reads source files as text and never evaluates an expression, so a
 * class built by interpolation generates no rule and the bar renders
 * uncoloured with the build still passing. The map keeps every class literal.
 */
const FILL: Record<Tone, string> = {
  primary: 'bg-primary',
  secondary: 'bg-secondary',
  tertiary: 'bg-tertiary',
  warning: 'bg-warning',
  error: 'bg-error',
}

export function ProgressBar({ value, max, tone = 'secondary' }: { value: number; max: number; tone?: Tone }) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0
  return (
    <div className="h-1 w-full overflow-hidden rounded-full bg-surface-container-highest">
      <div className={`h-full rounded-full ${FILL[tone]} transition-[width] duration-300`} style={{ width: `${pct}%` }} />
    </div>
  )
}
```

For the remaining primitives — `Button`, `IconButton`, `Badge`, `Chip`, `Card`, `Toggle`, `SegmentedControl`, `Skeleton`, `EmptyState` — take the markup from the mockups, which already express these in the exact token classes. `Button` and `Chip` appear in `.redesign/home_dashboard_de_entrada_controle_homelab/code.html`; `SegmentedControl` and `Chip` with counts in `.redesign/biblioteca_principal_sincronizada_com_komga_provedores/code.html`; `Toggle` and `Card` in `.redesign/ajustes_configura_es_do_homelab_integra_es/code.html`. Translate every visible string to English. Export all of them from `frontend/src/ui/index.ts`.

- [ ] **Step 3: Write the shell**

Create `frontend/src/app/AppShell.tsx`. It owns: brand and version chip, seven-item navigation with live badges, the integration strip, a sync-all button, and `<Outlet />` inside a `max-w-canvas mx-auto px-margin` container. Badges come from the existing SSE subscription, not a timer — `useJobEvents` already exists and is the only refresh trigger.

```tsx
import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'

import { api } from '../lib/api'
import { useJobEvents } from '../lib/useEvents'
import { Badge, Button } from '../ui'
import { Icon, type IconName } from '../ui/Icon'

type Integration = { name: string; state: string; detail: string | null }

const NAV: { to: string; label: string; icon: IconName; badge?: 'review' | 'jobs' | 'suggestions' }[] = [
  { to: '/home', label: 'Home', icon: 'chart' },
  { to: '/library', label: 'Library', icon: 'book' },
  { to: '/review', label: 'Review', icon: 'check', badge: 'review' },
  { to: '/discovery', label: 'Discovery', icon: 'sparkle', badge: 'suggestions' },
  { to: '/downloads', label: 'Downloads', icon: 'download', badge: 'jobs' },
  { to: '/stats', label: 'Stats', icon: 'chart' },
  { to: '/settings', label: 'Settings', icon: 'settings' },
]

const STRIP_LABEL: Record<string, string> = {
  mal: 'MyAnimeList', anilist: 'AniList', mangadex: 'MangaDex', komga: 'Komga', comick: 'Comick',
}

const DOT: Record<string, string> = {
  ok: 'bg-secondary', unauthenticated: 'bg-warning', unreachable: 'bg-error',
}

export function AppShell() {
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [reviewCount, setReviewCount] = useState(0)
  const [integrations, setIntegrations] = useState<Integration[]>([])

  const refresh = () => {
    api.jobCounts().then(setCounts).catch(() => undefined)
    api.series('needs_review').then((s) => setReviewCount(s.length)).catch(() => undefined)
    api.integrations().then(setIntegrations).catch(() => undefined)
  }

  useEffect(refresh, [])
  useJobEvents(refresh)

  const badges: Record<string, number> = {
    review: reviewCount,
    jobs: (counts.leased ?? 0) + (counts.pending ?? 0),
    suggestions: 0, // wired when the discovery backend lands
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="fixed inset-x-0 top-0 z-50 h-20 border-b border-white/5 bg-surface-container-lowest/80 backdrop-blur-xl">
        <div className="flex h-full items-center justify-between gap-space-md px-gutter">
          <div className="flex shrink-0 items-center gap-space-lg">
            <div className="flex items-center gap-space-sm">
              <span className="text-headline-sm tracking-tight text-on-surface">KuroManga</span>
              <span className="rounded bg-surface-container px-space-sm py-space-xs font-mono text-label-sm text-primary">
                self-hosted
              </span>
            </div>
            <nav className="hidden items-center gap-space-xs xl:flex">
              {NAV.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `flex items-center gap-space-xs rounded-lg px-space-sm py-space-xs transition-colors ${
                      isActive
                        ? 'bg-surface-container-high text-title-md text-on-surface'
                        : 'text-on-surface-variant hover:bg-surface-container hover:text-on-surface'
                    }`
                  }
                >
                  {item.label}
                  {item.badge && badges[item.badge] > 0 && (
                    <Badge tone="secondary">{badges[item.badge]}</Badge>
                  )}
                </NavLink>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-space-md">
            <div className="hidden items-center gap-space-sm rounded bg-surface-container-lowest px-space-sm py-space-xs 2xl:flex">
              {integrations.map((item) => (
                <span key={item.name} className="flex items-center gap-1.5 font-mono text-label-sm text-on-surface-variant">
                  <span className={`h-2 w-2 rounded-full ${DOT[item.state] ?? 'bg-outline'}`} />
                  {STRIP_LABEL[item.name] ?? item.name}
                </span>
              ))}
            </div>
            <Button variant="surface" size="sm" icon="sync" onClick={() => { api.sync('mal'); api.sync('anilist') }}>
              Sync all
            </Button>
          </div>
        </div>
      </header>
      <main className="pt-20">
        <div className="mx-auto flex max-w-canvas flex-col gap-space-xl px-margin py-space-xl">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
```

The `suggestions: 0` line is deliberate and temporary: the badge has no source until the discovery backend exists, and showing zero is honest where inventing a number is not. Plan B replaces it.

Two things the sample above does not show, both required:

**The header nav is `xl:` only, so it needs a complement.** Below that width the sample leaves no way to reach any screen but the URL bar, which fails the constraint that every screen is usable at 640 px. `DESIGN.md`'s responsive section specifies the answer — a compact navigation pinned to the bottom — so implement that rather than inventing a pattern. The bar's breakpoint must be the exact complement of the header nav's: no width where both show, and none where neither does. The main container gains bottom padding at those widths so the bar never covers content. This is where each `NAV` entry's `icon` field earns its place.

**The status dots need a text alternative.** Colour is the sample's only signal for `ok` / `unauthenticated` / `unreachable`, and the adjacent text is just the provider's name, so a screen reader announces "MyAnimeList" and nothing about its health. Add visually hidden text stating the state, keyed off the same `item.state` the dot reads so the two cannot drift. The visible design does not change.

- [ ] **Step 4: Move the client, add the new call, rewrite the routes**

Move `src/api.ts` to `src/lib/api.ts` and `src/useEvents.ts` to `src/lib/useEvents.ts` with `git mv`, fixing imports in the four existing pages. Add to the `api` object:

```ts
  integrations: () =>
    request<{ integrations: { name: string; state: string; detail: string | null }[] }>(
      '/api/health/integrations',
    ).then((body) => body.integrations),
```

Create `src/app/routes.tsx` with the shell as the layout route and the four screens that exist today as children, `/home`, `/discovery` and `/stats` omitted until their tasks land. Reduce `src/App.tsx` to rendering that route table.

- [ ] **Step 5: Verify the build**

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 6: Verify in the browser**

Start the stack and open the interface:

```bash
docker compose build api && docker compose up -d --force-recreate api worker
cd frontend && npm run dev
```

Open `http://localhost:5173`. Confirm: navigation highlights the active route, the integration strip shows five dots, badges appear only when non-zero, and the layout holds at 640 px width.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/ui frontend/src/app frontend/src/lib frontend/src/App.tsx
git commit -m "feat(web): build the application shell and shared primitives

Navigation, live badges and integration status belong to the shell rather than
to each screen, so a screen cannot disagree with its neighbour about what the
pipeline is doing."
```

---

### Task 4: Series API — status, progress and the forward-only write

Closes #8.

**Files:**
- Modify: `backend/app/enums.py`, `backend/app/api/routes_series.py`
- Create: `backend/app/handlers/progress_write.py`, `backend/tests/test_progress_write.py`
- Test: `backend/tests/test_progress_write.py`, `backend/tests/test_api.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `GET /api/series` gains `status: str | null`, `progress: int`, `score: float | null`, `genres: list[str]`, `format: str | null`, `updated_at: str | null`.
  - `score` is on a ten-point scale with one decimal, whichever provider it came from. AniList reports 0–100 and MyAnimeList 0–10, so AniList's is divided by ten at extraction. Normalising here rather than in the view keeps the units error legible as a bug: once a screen renders `82` beside `8.9`, it starts reading as a design choice. Absent is not zero — both providers omit the score for titles too few people have rated, and that stays `null`.
  - Both providers' list queries must actually request the score and format fields. Extraction is correct and useless if the query never asks.
  - `POST /api/series/{id}/progress` with body `{"chapter": int}` returning `{"progress": int, "queued": bool}`.
  - `JobType.PROGRESS_WRITE` with payload `{"series_id": int, "chapter": int}`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_progress_write.py`:

```python
"""The forward-only guard.

This is the one place a bug writes wrong data to somebody else's service, where
it cannot be rolled back by fixing our database.
"""

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.handlers.progress_write import forward_only

pytestmark = pytest.mark.asyncio


def test_forward_only_allows_a_higher_chapter():
    assert forward_only(current=10, requested=11) == 11


def test_forward_only_rejects_a_lower_chapter():
    assert forward_only(current=10, requested=4) is None


def test_forward_only_rejects_an_equal_chapter():
    assert forward_only(current=10, requested=10) is None
```

Append to `backend/tests/test_api.py`:

```python
async def test_series_rows_carry_status_and_progress(client):
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug) values ('Sakamoto Days', 'sakamoto-days');
                insert into list_entry
                       (provider, provider_media_id, series_id, status, user_progress_chapter,
                        total_chapters, synonyms, raw)
                values ('anilist', '1', 1, 'reading', 164, 200, '[]'::jsonb,
                        '{"averageScore": 82, "genres": ["Action"], "format": "MANGA"}'::jsonb)
                """
            )
        )
        await session.commit()

    row = (await client.get("/api/series")).json()[0]
    assert row["status"] == "reading"
    assert row["progress"] == 164
    assert row["score"] == 82
    assert row["genres"] == ["Action"]
    assert row["format"] == "MANGA"


async def test_progress_cannot_move_backwards(client):
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug) values ('Dandadan', 'dandadan');
                insert into list_entry
                       (provider, provider_media_id, series_id, status, user_progress_chapter, synonyms, raw)
                values ('anilist', '2', 1, 'reading', 140, '[]'::jsonb, '{}'::jsonb)
                """
            )
        )
        await session.commit()

    response = await client.post("/api/series/1/progress", json={"chapter": 3})
    assert response.status_code == 409
    assert (await client.get("/api/series")).json()[0]["progress"] == 140
```

`test_api.py` already imports `get_sessionmaker` and `text`; no new imports are needed.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend && POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest \
  tests/test_progress_write.py tests/test_api.py -k "progress or status_and_progress" -q
```

Expected: FAIL — `ModuleNotFoundError: app.handlers.progress_write`, and `KeyError: 'status'`.

- [ ] **Step 3: Add the job type**

In `backend/app/enums.py`, add to `JobType`:

```python
    PROGRESS_WRITE = "progress_write"
```

- [ ] **Step 4: Write the handler**

Create `backend/app/handlers/progress_write.py`:

```python
"""A chapter the user recorded by hand, pushed to the lists.

progress_push derives progress from Komga. This is the other direction: a
number the user stated. It is a separate job from LIST_WRITE on purpose — the
product brief's rule is that a status write never carries progress, and two
jobs cannot blur into one the way two branches of one job can.

The forward-only guard is shared with progress_push for the same reason it
exists there: a list that already records more must never be lowered by us.
"""

from sqlalchemy import text

from app.enums import JobType, Provider
from app.handlers.base import JobContext, PermanentError, register
from app.providers import get_source
from app.providers.tokens import access_token_for


def forward_only(current: int, requested: int) -> int | None:
    """The chapter to write, or None when it would not move the list forward."""
    return requested if requested > current else None


@register(JobType.PROGRESS_WRITE)
async def handle(ctx: JobContext) -> None:
    series_id = int(ctx.payload["series_id"])
    chapter = int(ctx.payload["chapter"])

    result = await ctx.session.execute(
        text(
            """
            select e.id, e.provider, e.provider_media_id, e.user_progress_chapter
              from list_entry e
              join provider_token t on t.provider = e.provider
             where e.series_id = :series_id
            """
        ),
        {"series_id": series_id},
    )
    entries = result.all()
    if not entries:
        raise PermanentError(f"series {series_id} has no connected list entry")

    pushed = 0
    for entry in entries:
        target = forward_only(entry.user_progress_chapter, chapter)
        if target is None:
            await ctx.log(f"{entry.provider}: already at chapter {entry.user_progress_chapter}")
            continue
        provider = Provider(entry.provider)
        token = await access_token_for(ctx.session, provider)
        await get_source(provider).push_progress(token, entry.provider_media_id, target)
        await ctx.session.execute(
            text("update list_entry set user_progress_chapter = :n where id = :id"),
            {"n": target, "id": entry.id},
        )
        await ctx.log(f"{provider}: progress set to chapter {target}")
        pushed += 1

    await ctx.log(f"chapter {chapter} recorded, {pushed} lists updated", pct=100)
```

Register the module wherever the existing handlers are imported for their side effect — check `app/handlers/__init__.py` and `app/worker/runner.py`, and follow whichever pattern is already there. A handler that is written but never imported produces the `no handler registered` failure the project README warns about.

- [ ] **Step 5: Extend the series query and add the route**

In `backend/app/api/routes_series.py`, extend `LIST_SQL`'s select list. The provider payload differs between AniList and MyAnimeList, so read both shapes and prefer whichever is present:

```sql
       (array_agg(e.status order by e.updated_at desc))[1] as status,
       coalesce(max(e.user_progress_chapter), 0) as progress,
       max(e.updated_at) as updated_at,
       (array_agg(e.raw order by e.updated_at desc))[1] as raw
```

and in the row builder, read the display-only fields out of `raw` rather than adding columns:

```python
def _from_raw(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Score, genres and format are display-only.

    They live in the payload the provider already sent. A column for each would
    be three more things to keep in sync for no behaviour.
    """
    raw = raw or {}
    node = raw.get("node") or raw  # MyAnimeList nests; AniList does not.
    score = node.get("averageScore") or node.get("mean")
    return {
        "score": float(score) if score is not None else None,
        "genres": node.get("genres") or [g["name"] for g in node.get("genres", []) if isinstance(g, dict)],
        "format": node.get("format") or node.get("media_type"),
    }
```

Add the route:

```python
class ProgressIn(BaseModel):
    chapter: int


@router.post("/{series_id}/progress")
async def set_progress(series_id: int, body: ProgressIn, session: Session) -> dict[str, Any]:
    # min, not max: a series can sit at different chapters on each provider, and
    # a write that advances the lagging one is legitimate. Refuse only when it
    # would be a no-op everywhere. The handler still guards each entry.
    result = await session.execute(
        text("select coalesce(min(user_progress_chapter), 0) as current from list_entry where series_id = :id"),
        {"id": series_id},
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="series not found")
    if forward_only(row.current, body.chapter) is None:
        raise HTTPException(status_code=409, detail="progress cannot move backwards")

    await repo.enqueue(
        session, JobType.PROGRESS_WRITE, {"series_id": series_id, "chapter": body.chapter}, priority=0
    )
    await session.commit()
    return {"progress": body.chapter, "queued": True}
```

Match `repo.enqueue`'s real signature — read `app/queue/repo.py` and follow how `routes_jobs.py` already calls it rather than assuming these argument names.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd backend && POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests -q
```

Expected: PASS, the whole suite, no regressions in `test_api.py` or `test_progress_push.py`.

- [ ] **Step 7: Lint and commit**

```bash
cd backend && .venv/bin/python -m ruff check app/ tests/
git add backend/app/enums.py backend/app/api/routes_series.py \
        backend/app/handlers/progress_write.py backend/tests/
git commit -m "feat(api): expose reading status and record progress by hand

Status and progress were already synced and already correct; the library just
could not see them. The manual write is its own job type rather than a branch
of LIST_WRITE, because a status write must never be able to carry progress."
```

---

### Task 5: Library screen

Closes #9.

**Files:**
- Create: `frontend/src/features/library/{LibraryPage,SeriesGrid,SeriesTable,CoverCard,QuickIncrement,ContinueReading,StatusTabs}.tsx`, `frontend/src/features/library/useLibrary.ts`
- Delete: `frontend/src/pages/Library.tsx`, `frontend/src/styles.css`
- Test: build and browser — see Steps 5 and 6

**Interfaces:**
- Consumes: Task 3's primitives and `formatChapter`; Task 4's extended `GET /api/series` and `POST /api/series/{id}/progress`.
- Produces: `useLibrary()` returning `{ series, status, setStatus, view, setView, query, setQuery, increment }`, where `increment(id: number, next: number): Promise<void>` applies optimistically and rolls back on rejection.

- [ ] **Step 1: Write the optimistic increment hook**

The behaviour worth getting right on this screen. It updates first and reconciles after, because a control whose whole point is one click cannot wait for a round trip.

Create `frontend/src/features/library/useLibrary.ts`:

```ts
import { useCallback, useEffect, useState } from 'react'

import { api, type Series } from '../../lib/api'
import type { ListStatus } from '../../lib/format'

export type View = 'grid' | 'table'

export function useLibrary() {
  const [series, setSeries] = useState<Series[]>([])
  const [status, setStatus] = useState<ListStatus | 'all'>('reading')
  const [view, setView] = useState<View>('grid')
  const [query, setQuery] = useState('')

  const load = useCallback(() => {
    api.series().then(setSeries).catch(() => undefined)
  }, [])

  useEffect(load, [load])

  /**
   * Apply, then confirm. A rejected write restores the previous number
   * visibly: silently reverting reads as the click having missed.
   */
  const increment = useCallback(async (id: number, next: number) => {
    const previous = series
    setSeries((rows) => rows.map((row) => (row.id === id ? { ...row, progress: next } : row)))
    try {
      await api.setProgress(id, next)
    } catch (error) {
      setSeries(previous)
      throw error
    }
  }, [series])

  const visible = series.filter((row) => {
    const matchesStatus = status === 'all' || row.status === status
    const matchesQuery = !query || row.title.toLowerCase().includes(query.toLowerCase())
    return matchesStatus && matchesQuery
  })

  return { series: visible, all: series, status, setStatus, view, setView, query, setQuery, increment, reload: load }
}
```

Add to `lib/api.ts`:

```ts
  setProgress: (id: number, chapter: number) =>
    request<{ progress: number; queued: boolean }>(`/api/series/${id}/progress`, {
      method: 'POST',
      body: JSON.stringify({ chapter }),
    }),
```

and extend the `Series` interface with `status: ListStatus | null`, `progress: number`, `score: number | null`, `genres: string[]`, `format: string | null`, `updated_at: string | null`.

- [ ] **Step 2: Write the cover card and quick increment**

`CoverCard.tsx` renders a 2:3 cover with `rounded-lg`, a hairline `border-white/[0.08]`, badges overlaying the art, the progress track docked flush along the bottom edge of the image, and the title *below* the image — a long romanised title must not cover the art it names. Hover is `-translate-y-1` with `shadow-glow` and an image scale of `1.03`.

`QuickIncrement.tsx` is the `+1 Ch` control: a 32 px glass button, `bg-surface-container/85 backdrop-blur-sm border border-white/15`, which calls `increment` and flashes `bg-secondary` for 400 ms on success. On rejection it restores and flashes `bg-error` instead, so a failed click is visible rather than silent.

Markup reference: `.redesign/biblioteca_principal_sincronizada_com_komga_provedores/code.html` — the card grid and the `incrementChapter` handler near the end of that file. Translate every string.

- [ ] **Step 3: Write the tabs, the two views and the page**

`StatusTabs.tsx` renders `Chip` per status with a live count taken from `all`, plus an "All" chip. `SeriesGrid.tsx` is an auto-fill grid, `minmax(160px, 220px)`, 2 columns under 640 px. `SeriesTable.tsx` renders the same rows as a table with a `64px` row height whose chapter cell edits inline through the same `increment`. `ContinueReading.tsx` shows the three most recently updated `reading` rows. `LibraryPage.tsx` composes them and switches views with `SegmentedControl`.

- [ ] **Step 4: Remove the old page and stylesheet**

```bash
git rm frontend/src/pages/Library.tsx frontend/src/styles.css
```

Point the `/library` route at `features/library/LibraryPage`. Confirm nothing still imports `styles.css`:

```bash
cd frontend && grep -rn "styles.css" src/ index.html || echo "clean"
```

Expected: `clean`.

- [ ] **Step 5: Verify the build**

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 6: Verify in the browser**

With the stack running, open `/library`. Confirm: status tabs filter and their counts match, the grid reflows to 2 columns at 640 px, `+1 Ch` increments immediately, and a second click that would exceed a stale total still reconciles rather than sticking at the optimistic value. Force a rejection by clicking `+1 Ch` on a series whose progress is already the highest recorded, and confirm the number visibly returns.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/features/library frontend/src/lib/api.ts frontend/src/app/routes.tsx
git commit -m "feat(web): rebuild the library on real status and progress

Grid and table are two renderings of one fetched list. The +1 Ch control
applies before the round trip and rolls back visibly, because a control whose
point is one click cannot wait for the network to agree."
```

---

### Task 6: Review and downloads screens

Closes #10.

**Files:**
- Create: `frontend/src/features/review/ReviewPage.tsx`, `frontend/src/features/review/CandidateCard.tsx`, `frontend/src/features/downloads/DownloadsPage.tsx`, `frontend/src/features/downloads/JobRow.tsx`, `frontend/src/features/downloads/JobEventLog.tsx`
- Delete: `frontend/src/pages/Review.tsx`, `frontend/src/pages/Downloads.tsx`
- Test: build and browser

**Interfaces:**
- Consumes: Task 3's primitives; the existing `api.candidates`, `api.confirmMapping`, `api.research`, `api.jobs`, `api.jobEvents`, `api.retry`.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Port the review screen**

Move the logic from `pages/Review.tsx` unchanged and restyle it with the primitives. Candidate cards show cover, title, chapter count and year, with the score rendered as a `ProgressBar`, and the confirm action as a `Button variant="primary"`.

Confirming a mapping is one of the pipeline's two deliberate stops: a wrong match downloads the wrong manga for every future chapter. The redesign must not make it look incidental — the confirm button is the visual anchor of the card, not a link in a corner.

- [ ] **Step 2: Port the downloads screen**

Move the logic from `pages/Downloads.tsx` unchanged and restyle it. Job rows carry a `StatusPill`-shaped state badge, a `ProgressBar` fed by `pct`, and an expandable `JobEventLog`. Retry stays a `Button variant="surface"`.

Progress keeps arriving over the existing SSE subscription. Nothing here introduces a timer.

- [ ] **Step 3: Delete the old pages and repoint the routes**

```bash
git rm frontend/src/pages/Review.tsx frontend/src/pages/Downloads.tsx
```

- [ ] **Step 4: Verify the build**

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 5: Verify in the browser**

Queue a sync so jobs exist, then open `/downloads` and confirm rows appear and progress advances without a page refresh. Open `/review` and confirm a candidate can still be confirmed.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/review frontend/src/features/downloads frontend/src/app/routes.tsx
git commit -m "feat(web): restyle the review and downloads screens

Confirming a mapping is one of the pipeline's two deliberate stops. The redesign
makes the confirm action the anchor of the card rather than a link in a corner."
```

---

### Task 7: Settings screen

Closes #11.

**Files:**
- Create: `frontend/src/features/settings/SettingsPage.tsx`, `frontend/src/features/settings/{ProviderCard,SourceCard,PipelineFields,StorageFields}.tsx`
- Modify: `backend/app/settings_store.py`
- Delete: `frontend/src/pages/Settings.tsx`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: Task 3's primitives; Task 2's `GET /api/health/integrations`; the existing settings endpoints.
- Produces: four new setting keys — `cron_anime_sync` (default `0 */12 * * *`), `comick_url` (default `""`), `comick_enabled` (default `false`), `reading_minutes_per_chapter` (default `8`). Plan C reads the last one.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_api.py`:

```python
async def test_settings_expose_the_new_pipeline_keys(client):
    values = (await client.get("/api/settings")).json()["values"]
    assert values["cron_anime_sync"] == "0 */12 * * *"
    assert values["reading_minutes_per_chapter"] == "8"
    assert "comick_url" in values
    assert values["comick_enabled"] == "false"
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest \
  tests/test_api.py -k new_pipeline_keys -q
```

Expected: FAIL with `KeyError: 'cron_anime_sync'`.

- [ ] **Step 3: Add the keys**

In `backend/app/settings_store.py`, follow the existing pattern exactly — a module constant, a field on `Defaults`, and a branch in the default lookup:

```python
CRON_ANIME_SYNC = "cron_anime_sync"
COMICK_URL = "comick_url"
COMICK_ENABLED = "comick_enabled"
READING_MINUTES_PER_CHAPTER = "reading_minutes_per_chapter"
```

with defaults `"0 */12 * * *"`, `""`, `False`, `8`. Twelve hours for the anime sync because an anime list changes when an episode airs, not continuously, and the discovery pass it feeds is expensive.

- [ ] **Step 4: Run it to verify it passes**

```bash
cd backend && POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest \
  tests/test_api.py -q
```

Expected: PASS, whole file.

- [ ] **Step 5: Write the screen**

Four sections, following `.redesign/ajustes_configura_es_do_homelab_integra_es/code.html`: list providers with OAuth state and a connect or disconnect action; download sources with the MangaDex and Comick cards and the Comick enable toggle; pipeline and queue tuning with the six numeric and cron fields; Komga and storage with the library path and the automation toggles. A sticky action bar saves.

Provider connection state comes from `GET /api/health/integrations`, the same source the header strip reads, so the two can never disagree.

- [ ] **Step 6: Delete the old page, verify the build, verify in the browser**

```bash
git rm frontend/src/pages/Settings.tsx
cd frontend && npm run build
```

Open `/settings`, change `download_batch_size`, save, reload, and confirm the value persisted.

- [ ] **Step 7: Lint and commit**

```bash
cd backend && .venv/bin/python -m ruff check app/ tests/
git add backend/app/settings_store.py backend/tests/test_api.py \
        frontend/src/features/settings frontend/src/app/routes.tsx
git commit -m "feat(web): restyle settings and expose the pipeline configuration

Connection state is read from the same endpoint the header strip uses, so the
two cannot disagree about whether a provider is authenticated."
```

---

### Task 8: Series detail screen

Closes #12.

**Files:**
- Create: `frontend/src/features/series/{SeriesDetailPage,ChapterTable,MappingPanel,SyncTargets}.tsx`
- Modify: `backend/app/api/routes_series.py`, `frontend/src/app/routes.tsx`, `frontend/src/lib/api.ts`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: Task 3's primitives; Task 4's `LIST_SQL` extension.
- Produces: `GET /api/series/{id}` returning `{series: {...the list row...}, mapping: {source_site, source_url} | null, chapters: [{number, title, state, file_path}], entries: [{provider, provider_media_id, status, user_progress_chapter, updated_at}]}`, and the route `/series/:id`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_api.py`:

```python
async def test_series_detail_returns_chapters_and_entries(client):
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug) values ('Eleceed', 'eleceed');
                insert into list_entry
                       (provider, provider_media_id, series_id, status, user_progress_chapter, synonyms, raw)
                values ('mal', '7', 1, 'reading', 280, '[]'::jsonb, '{}'::jsonb);
                insert into chapter (series_id, number, title, state)
                values (1, 280, 'Kayden', 'downloaded')
                """
            )
        )
        await session.commit()

    body = (await client.get("/api/series/1")).json()
    assert body["series"]["title"] == 'Eleceed'
    assert [c["state"] for c in body["chapters"]] == ["downloaded"]
    assert [e["provider"] for e in body["entries"]] == ["mal"]


async def test_series_detail_for_a_missing_series_is_a_404(client):
    assert (await client.get("/api/series/999999")).status_code == 404
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest \
  tests/test_api.py -k series_detail -q
```

Expected: FAIL. Note the existing `/{series_id}/candidates` route does not match a bare `/{series_id}`, so this is a 404 from a missing route rather than a collision.

- [ ] **Step 3: Write the route**

Add to `backend/app/api/routes_series.py`, placed **after** the `GET ""` list route and **before** the `/{series_id}/…` routes so path matching stays unambiguous:

```python
@router.get("/{series_id}")
async def series_detail(series_id: int, session: Session) -> dict[str, Any]:
    result = await session.execute(text(LIST_SQL_ONE), {"id": series_id})
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="series not found")

    chapters = await session.execute(
        text(
            """
            select number, title, state, file_path, komga_book_id
              from chapter where series_id = :id order by number
            """
        ),
        {"id": series_id},
    )
    entries = await session.execute(
        text(
            """
            select provider, provider_media_id, status, user_progress_chapter, updated_at
              from list_entry where series_id = :id order by provider
            """
        ),
        {"id": series_id},
    )
    return {
        "series": _row_to_series(row),
        "mapping": {"source_site": row.source_site, "source_url": row.source_url}
        if row.source_url
        else None,
        "chapters": [dict(c._mapping) for c in chapters.all()],
        "entries": [dict(e._mapping) for e in entries.all()],
    }
```

`LIST_SQL_ONE` is `LIST_SQL` with `where s.id = :id` inserted before the `group by`, and `_row_to_series` is the existing row builder from the list route extracted into a function so both routes produce the same shape. Extract it rather than duplicating: two builders drift, and the detail page would quietly start disagreeing with the card the user clicked.

- [ ] **Step 4: Run it to verify it passes**

```bash
cd backend && POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/python -m pytest tests -q
```

Expected: PASS, whole suite.

- [ ] **Step 5: Write the screen**

`SeriesDetailPage.tsx` at route `/series/:id`: cover and metadata header, `MappingPanel` showing the confirmed source with a re-run-search action, `SyncTargets` listing each provider entry with its status and last write, `ChapterTable` listing chapters with local file state, and the per-series controls — the `auto_download` toggle and a download-range form, both calling the existing endpoints.

Make the library's cover cards link here.

- [ ] **Step 6: Verify the build and the browser**

```bash
cd frontend && npm run build
```

Open `/library`, click a cover, confirm the detail page loads with chapters listed and the auto-download toggle reflecting the stored value.

- [ ] **Step 7: Lint and commit**

```bash
cd backend && .venv/bin/python -m ruff check app/ tests/
git add backend/app/api/routes_series.py backend/tests/test_api.py \
        frontend/src/features/series frontend/src/lib/api.ts frontend/src/app/routes.tsx
git commit -m "feat(web): add a series detail screen

The list route's row builder is extracted and shared rather than copied: two
builders drift, and the detail page would quietly disagree with the card the
user clicked to reach it."
```

---

## Self-Review

**Spec coverage.** Spec sections map to tasks as follows: the design system to Task 1; primitives and shell to Task 3; the integration strip to Task 2; Library to Task 5; Series detail to Task 8; Settings to Task 7; the series API extension, `PROGRESS_WRITE` and the golden rule to Task 4; Review and Downloads to Task 6.

Deliberately **not** covered here, and carried to later plans: Home and Stats, `progress_event`, `GET /api/dashboard`, `GET /api/stats` (Plan C); Discovery, `anime_entry`, `suggestion`, `ANIME_LIST_SYNC`, `SUGGEST_BUILD`, `LIST_WRITE`, MangaDex as a list provider, and the `ListSource` additions `fetch_anime_list` / `push_status` / `add_to_list` (Plan B). The spec's acceptance criteria 7, 8 and 9 belong to those plans; 1 through 6 and 10 are provable at the end of this one.

**Type consistency.** `ListStatus` is defined once in `lib/format.ts` and imported everywhere. `Series.progress` is the name in the API row, the `useLibrary` state and the increment call. `forward_only(current, requested)` is called with keyword arguments in its test and positionally in the handler, which matches its signature. `IconName` is exported from `Icon.tsx` and consumed by `AppShell` and `Button`.

**Known approximation.** Three places tell the implementer to read existing code rather than trusting a signature written here: `repo.enqueue`'s arguments, `settings_store`'s accessor, and where handler modules get imported for registration. These are real call sites in the repository that this plan should not restate from memory — the project's own guidance is that contracts get read from the source, not recalled.
