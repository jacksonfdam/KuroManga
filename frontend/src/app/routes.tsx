import { Navigate, Route, Routes } from 'react-router-dom'

import { DiscoverPage } from '../features/discover/DiscoverPage'
import { DownloadsPage } from '../features/downloads/DownloadsPage'
import { HomePage } from '../features/home/HomePage'
import { LibraryPage } from '../features/library/LibraryPage'
import { SeriesDetailPage } from '../features/series/SeriesDetailPage'
import { SettingsPage } from '../features/settings/SettingsPage'
import { StatsPage } from '../features/stats/StatsPage'
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
// later; the screen exists now, so it is named in the nav like any other.

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<HomePage />} />
        <Route path="stats" element={<StatsPage />} />
        <Route path="library" element={<LibraryPage />} />
        <Route path="series/:id" element={<SeriesDetailPage />} />
        <Route path="discover" element={<DiscoverPage />} />
        {/* The three screens Discover replaces. Redirected rather than
            removed: these addresses are in browser history and in docs/, and
            a dead link is a worse answer than a moved one. */}
        <Route path="discovery" element={<Navigate to="/discover" replace />} />
        <Route path="unmatched" element={<Navigate to="/discover" replace />} />
        <Route path="review" element={<Navigate to="/discover" replace />} />
        <Route path="downloads" element={<DownloadsPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  )
}
