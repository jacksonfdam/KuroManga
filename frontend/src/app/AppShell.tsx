import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'

import { api, messageOf } from '../lib/api'
import { useJobEvents } from '../lib/useEvents'
import { useNotice } from '../lib/useNotice'
import { Badge, Button, NoticeBar } from '../ui'
import { Icon, type IconName } from '../ui/Icon'

type Integration = { name: string; state: string; detail: string | null }

// Home and Stats are omitted: their screens belong to later plans (see
// task-4..8 in this spec set), and a nav item that leads nowhere is worse than
// a nav that grows later. Discovery and its unmatched list are routed, so they
// are named here.
const NAV: { to: string; label: string; icon: IconName; badge?: 'review' | 'jobs' | 'suggestions' }[] = [
  { to: '/library', label: 'Library', icon: 'book' },
  { to: '/discovery', label: 'Discovery', icon: 'sparkle', badge: 'suggestions' },
  { to: '/unmatched', label: 'Unmatched', icon: 'search' },
  { to: '/review', label: 'Review', icon: 'check', badge: 'review' },
  { to: '/downloads', label: 'Downloads', icon: 'download', badge: 'jobs' },
  { to: '/settings', label: 'Settings', icon: 'settings' },
]

const STRIP_LABEL: Record<string, string> = {
  mal: 'MyAnimeList', anilist: 'AniList', mangadex: 'MangaDex', komga: 'Komga', comick: 'Comick',
}

const DOT: Record<string, string> = {
  ok: 'bg-secondary', unauthenticated: 'bg-warning', unreachable: 'bg-error',
}

// The dot is colour-only. A screen reader needs the state in words too, or it
// announces the provider's name and nothing about whether it's working.
const STATE_LABEL: Record<string, string> = {
  ok: 'reachable', unauthenticated: 'needs sign-in', unreachable: 'unreachable',
}

// Named here rather than reusing the strip's map, because the strip lists
// every integration and only the two list providers are synced.
const SYNCED: [string, string][] = [
  ['mal', 'MyAnimeList'],
  ['anilist', 'AniList'],
]

export function AppShell() {
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [reviewCount, setReviewCount] = useState(0)
  const [suggestionCount, setSuggestionCount] = useState(0)
  const [integrations, setIntegrations] = useState<Integration[]>([])
  const { notice, report, fail } = useNotice()

  // These four feed badges and the status strip, not the screen below. A
  // failure here degrades those to zero and to nothing, which the screens
  // themselves report properly, so it stays quiet rather than covering every
  // page with a banner the user cannot act on.
  const refresh = () => {
    api.jobCounts().then(setCounts).catch(() => undefined)
    api.series('needs_review').then((s) => setReviewCount(s.length)).catch(() => undefined)
    api.suggestionCounts().then((c) => setSuggestionCount(c.new ?? 0)).catch(() => undefined)
    api.integrations().then(setIntegrations).catch(() => undefined)
  }

  useEffect(refresh, [])
  useJobEvents(refresh)

  // The shell's own primary action. An unauthenticated provider rejects, and
  // firing both promises without looking at either meant the click reported
  // nothing at all — allSettled so one dead provider does not hide the other
  // one having worked.
  const syncAll = async () => {
    const results = await Promise.allSettled(SYNCED.map(([provider]) => api.sync(provider)))
    const failures = results.flatMap((result, index) =>
      result.status === 'rejected' ? [`${SYNCED[index][1]}: ${messageOf(result.reason)}`] : [],
    )
    if (failures.length > 0) fail(failures.join(' · '))
    else report('Sync queued for MyAnimeList and AniList')
  }

  const badges: Record<string, number> = {
    review: reviewCount,
    jobs: (counts.leased ?? 0) + (counts.pending ?? 0),
    suggestions: suggestionCount,
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
                  <span aria-hidden="true" className={`h-2 w-2 rounded-full ${DOT[item.state] ?? 'bg-outline'}`} />
                  {STRIP_LABEL[item.name] ?? item.name}
                  <span className="sr-only"> ({STATE_LABEL[item.state] ?? item.state})</span>
                </span>
              ))}
            </div>
            <Button variant="surface" size="sm" icon="sync" onClick={syncAll}>
              Sync all
            </Button>
          </div>
        </div>
      </header>
      {/* The header nav is `hidden xl:flex` (verbatim from the design spec's desktop
          mockups), which left nothing below 1280px — DESIGN.md's own responsive
          section calls for compact navigation pinned to the bottom, so this mirrors
          the header's breakpoint rather than inventing a separate tablet layout. */}
      <main className="pb-20 pt-20 xl:pb-0">
        {/* DESIGN.md's responsive section: 1rem outer margin below 640px, 2rem at
            and above it — space-md and margin are exactly those tokens. */}
        <div className="mx-auto flex max-w-canvas flex-col gap-space-xl px-space-md py-space-xl sm:px-margin">
          {/* Above the outlet rather than in the header: the header is one
              fixed row and the notice has to stay readable at phone width. */}
          {notice && <NoticeBar tone={notice.tone} text={notice.text} />}
          <Outlet context={refresh} />
        </div>
      </main>
      <nav className="fixed inset-x-0 bottom-0 z-50 flex items-center justify-around border-t border-white/5 bg-surface-container-lowest/95 px-gutter py-space-xs backdrop-blur-xl xl:hidden">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `flex flex-col items-center gap-0.5 rounded-lg px-space-sm py-space-xs transition-colors ${
                isActive ? 'text-primary' : 'text-on-surface-variant hover:text-on-surface'
              }`
            }
          >
            <span className="relative">
              <Icon name={item.icon} />
              {item.badge && badges[item.badge] > 0 && (
                <span className="absolute -right-2 -top-1.5">
                  <Badge tone="secondary">{badges[item.badge]}</Badge>
                </span>
              )}
            </span>
            <span className="font-mono text-label-sm">{item.label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
