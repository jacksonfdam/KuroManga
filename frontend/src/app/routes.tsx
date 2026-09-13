import { Navigate, Route, Routes, useOutletContext } from 'react-router-dom'

import { DiscoveryPage } from '../features/discovery/DiscoveryPage'
import { DownloadsPage } from '../features/downloads/DownloadsPage'
import { LibraryPage } from '../features/library/LibraryPage'
import { ReviewPage } from '../features/review/ReviewPage'
import { SeriesDetailPage } from '../features/series/SeriesDetailPage'
import { SettingsPage } from '../features/settings/SettingsPage'
import { UnmatchedPage } from '../features/unmatched/UnmatchedPage'
import { AppShell } from './AppShell'

// /home and /stats are deliberately absent: those screens belong to later
// plans, and a nav item that leads nowhere is worse than a nav that grows
// later. Discovery arrived with its backend and is routed below; the anime it
// could not match get their own route rather than a tab inside Discovery,
// because the two are different questions and the shell's nav is where this
// interface names a screen.

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
        <Route index element={<Navigate to="/library" replace />} />
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
