import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'

import { api } from '../lib/api'
import { useJobEvents } from '../lib/useEvents'
import { Badge, Button } from '../ui'
import { Icon, type IconName } from '../ui/Icon'

type Integration = { name: string; state: string; detail: string | null }

// Home, Discovery and Stats are omitted: their screens belong to later plans
// (see task-4..8 in this spec set), and a nav item that leads nowhere is
// worse than a nav that grows later.
const NAV: { to: string; label: string; icon: IconName; badge?: 'review' | 'jobs' | 'suggestions' }[] = [
  { to: '/library', label: 'Library', icon: 'book' },
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
                  <span aria-hidden="true" className={`h-2 w-2 rounded-full ${DOT[item.state] ?? 'bg-outline'}`} />
                  {STRIP_LABEL[item.name] ?? item.name}
                  <span className="sr-only"> ({STATE_LABEL[item.state] ?? item.state})</span>
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
          <Outlet context={refresh} />
        </div>
      </main>
    </div>
  )
}
