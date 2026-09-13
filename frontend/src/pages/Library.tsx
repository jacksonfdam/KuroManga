import { useEffect, useMemo, useState } from 'react'

import { api, type Series, type SeriesState } from '../api'
import { useJobEvents } from '../useEvents'

const FILTERS: Array<{ key: SeriesState | 'all'; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'mapped', label: 'Mapped' },
  { key: 'needs_review', label: 'Needs review' },
  { key: 'downloading', label: 'Downloading' },
  { key: 'failed', label: 'Failed' },
]

export function Library() {
  const [series, setSeries] = useState<Series[]>([])
  const [filter, setFilter] = useState<SeriesState | 'all'>('all')
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState<number | null>(null)

  const load = () => {
    api.series().then(setSeries).catch(() => undefined)
  }

  useEffect(load, [])
  useJobEvents((event) => {
    if (event.event !== 'job.progress') load()
  })

  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return series.filter(
      (item) =>
        (filter === 'all' || item.state === filter) &&
        (!needle || item.title.toLowerCase().includes(needle)),
    )
  }, [series, filter, query])

  const downloadAll = async (item: Series) => {
    setBusy(item.id)
    try {
      await api.download(item.id)
      load()
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      <h1>Library</h1>
      <p className="sub">
        {series.length} series tracked · {series.filter((s) => s.state === 'needs_review').length}{' '}
        waiting on a mapping
      </p>

      <div className="toolbar">
        {FILTERS.map((option) => (
          <button
            key={option.key}
            className={filter === option.key ? 'primary' : ''}
            onClick={() => setFilter(option.key)}
          >
            {option.label}
          </button>
        ))}
        <input
          placeholder="Filter by title"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>

      {shown.length === 0 ? (
        <div className="empty">Nothing here yet. Connect a list in Settings and run a sync.</div>
      ) : (
        <div className="grid">
          {shown.map((item) => (
            <article key={item.id} className="card">
              <div
                className="cover"
                style={item.cover_url ? { backgroundImage: `url(${item.cover_url})` } : undefined}
              />
              <div className="body">
                <span className="title">{item.title}</span>
                <div className="meta">
                  <span className={`pill ${item.state}`}>{item.state.replace('_', ' ')}</span>
                  {item.providers.map((provider) => (
                    <span key={provider} className="pill">
                      {provider}
                    </span>
                  ))}
                </div>
                <div className="meta">
                  {item.downloaded}/{item.known || item.total_chapters || '?'} chapters
                  {item.failed > 0 && <span style={{ color: 'var(--bad)' }}>{item.failed} failed</span>}
                </div>
                <div className="bar">
                  <span
                    style={{
                      width: `${item.known ? (100 * item.downloaded) / item.known : 0}%`,
                    }}
                  />
                </div>
                <div style={{ marginTop: 'auto', display: 'flex', gap: 6 }}>
                  <button
                    disabled={!item.source_url || busy === item.id}
                    onClick={() => downloadAll(item)}
                  >
                    Download missing
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </>
  )
}
