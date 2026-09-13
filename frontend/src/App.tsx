import { useEffect, useState } from 'react'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'

import { api } from './api'
import { Downloads } from './pages/Downloads'
import { Library } from './pages/Library'
import { Review } from './pages/Review'
import { Settings } from './pages/Settings'
import { useJobEvents } from './useEvents'

export function App() {
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [reviewCount, setReviewCount] = useState(0)

  const refreshBadges = () => {
    api.jobCounts().then(setCounts).catch(() => undefined)
    api
      .series('needs_review')
      .then((series) => setReviewCount(series.length))
      .catch(() => undefined)
  }

  useEffect(refreshBadges, [])
  useJobEvents(refreshBadges)

  const active = (counts.leased ?? 0) + (counts.pending ?? 0)

  return (
    <div className="shell">
      <header>
        <span className="brand">KuroManga</span>
        <nav>
          <NavLink to="/library">Library</NavLink>
          <NavLink to="/review">
            Review {reviewCount > 0 && <b className="badge">{reviewCount}</b>}
          </NavLink>
          <NavLink to="/downloads">
            Downloads {active > 0 && <b className="badge">{active}</b>}
          </NavLink>
          <NavLink to="/settings">Settings</NavLink>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Navigate to="/library" replace />} />
          <Route path="/library" element={<Library />} />
          <Route path="/review" element={<Review onResolved={refreshBadges} />} />
          <Route path="/downloads" element={<Downloads />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  )
}
