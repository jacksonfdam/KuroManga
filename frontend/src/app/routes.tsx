import { Navigate, Route, Routes, useOutletContext } from 'react-router-dom'

import { DownloadsPage } from '../features/downloads/DownloadsPage'
import { LibraryPage } from '../features/library/LibraryPage'
import { ReviewPage } from '../features/review/ReviewPage'
import { Settings } from '../pages/Settings'
import { AppShell } from './AppShell'

// /home, /discovery and /stats are deliberately absent: those screens belong
// to later plans, and a nav item that leads nowhere is worse than a nav that
// grows later.

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
        <Route path="review" element={<ReviewRoute />} />
        <Route path="downloads" element={<DownloadsPage />} />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  )
}
