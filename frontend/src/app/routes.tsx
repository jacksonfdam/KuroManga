import { Route, Routes, useOutletContext } from 'react-router-dom'

import { DiscoveryPage } from '../features/discovery/DiscoveryPage'
import { DownloadsPage } from '../features/downloads/DownloadsPage'
import { HomePage } from '../features/home/HomePage'
import { LibraryPage } from '../features/library/LibraryPage'
import { ReviewPage } from '../features/review/ReviewPage'
import { SeriesDetailPage } from '../features/series/SeriesDetailPage'
import { SettingsPage } from '../features/settings/SettingsPage'
import { StatsPage } from '../features/stats/StatsPage'
import { UnmatchedPage } from '../features/unmatched/UnmatchedPage'
import { AppShell } from './AppShell'

// Home is the index now. It was designed as its own section and `/` stood in
// for it with the library, which is a different screen answering a different
// question — the front page is the pipeline at a glance, and the library is
// the shelf. It lives at `/` rather than at `/home` so there is one address
// for the front page instead of a redirect and a duplicate.
//
// /stats is the second screen #16 asked for and #48 left unbuilt. It was
// deliberately absent while `GET /api/stats` had nothing consuming it, on the
// grounds that a nav item leading nowhere is worse than a nav that grows
// later; the screen exists now, so it is named in the nav like any other. The
// anime Discovery could not match get their own route rather than a tab inside
// it, because the two are different questions and the shell's nav is where
// this interface names a screen.

// Confirming a mapping should clear the shell's review badge immediately
// rather than waiting for the next SSE-triggered refresh, so Review's
// onResolved is wired to the same refresh AppShell passes down as context.
function ReviewRoute() {
  const refresh = useOutletContext<() => void>()
  return <ReviewPage onResolved={refresh} />
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<HomePage />} />
        <Route path="stats" element={<StatsPage />} />
        <Route path="library" element={<LibraryPage />} />
        <Route path="series/:id" element={<SeriesDetailPage />} />
        <Route path="discovery" element={<DiscoveryPage />} />
        <Route path="unmatched" element={<UnmatchedPage />} />
        <Route path="review" element={<ReviewRoute />} />
        <Route path="downloads" element={<DownloadsPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  )
}
