import { useCallback, useEffect, useState } from 'react'

import { api, type ReviewPayload, type Series } from '../lib/api'

/**
 * The mapping queue. This screen is the pipeline's only manual step, so it is
 * built to be cleared quickly: confirm advances straight to the next series.
 */
export function Review({ onResolved }: { onResolved: () => void }) {
  const [queue, setQueue] = useState<Series[]>([])
  const [current, setCurrent] = useState<ReviewPayload | null>(null)
  const [manualUrl, setManualUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadQueue = useCallback(async () => {
    const pending = await api.series('needs_review')
    setQueue(pending)
    if (pending.length > 0) {
      setCurrent(await api.candidates(pending[0].id))
    } else {
      setCurrent(null)
    }
    setManualUrl('')
    setError(null)
  }, [])

  useEffect(() => {
    loadQueue().catch((err) => setError(String(err)))
  }, [loadQueue])

  const confirm = useCallback(
    async (sourceUrl: string) => {
      if (!current || !sourceUrl) return
      setBusy(true)
      setError(null)
      try {
        await api.confirmMapping(current.series.id, sourceUrl)
        onResolved()
        await loadQueue()
      } catch (err) {
        setError(String(err))
      } finally {
        setBusy(false)
      }
    },
    [current, loadQueue, onResolved],
  )

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (!current || busy) return
      const index = Number(event.key)
      if (index >= 1 && index <= 9 && current.candidates[index - 1]) {
        confirm(current.candidates[index - 1].source_url)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [current, busy, confirm])

  if (!current) {
    return (
      <>
        <h1>Review</h1>
        <div className="empty">Nothing waiting. Every series has a confirmed source.</div>
      </>
    )
  }

  return (
    <>
      <h1>Review</h1>
      <p className="sub">
        {queue.length} waiting · press <span className="kbd">1</span>–<span className="kbd">9</span>{' '}
        to confirm a candidate
      </p>

      {error && <div className="panel row-error">{error}</div>}

      <div className="split">
        <aside className="panel">
          <div
            className="cover"
            style={{
              borderRadius: 8,
              marginBottom: 10,
              backgroundImage: current.series.cover_url
                ? `url(${current.series.cover_url})`
                : undefined,
            }}
          />
          <h2 style={{ margin: '0 0 6px' }}>{current.series.title}</h2>
          <div className="meta" style={{ flexDirection: 'column', gap: 2 }}>
            {[...new Set([...current.series.english, ...current.series.romaji])]
              .filter(Boolean)
              .map((title) => (
                <span key={title}>{title}</span>
              ))}
          </div>
          <div className="field" style={{ marginTop: 14 }}>
            <label>Paste a source URL instead</label>
            <input
              value={manualUrl}
              placeholder="https://mangadex.org/title/..."
              onChange={(event) => setManualUrl(event.target.value)}
            />
            <button disabled={!manualUrl || busy} onClick={() => confirm(manualUrl)}>
              Confirm this URL
            </button>
          </div>
          <button
            disabled={busy}
            onClick={() => api.research(current.series.id).then(() => undefined)}
          >
            Search again
          </button>
        </aside>

        <section>
          {current.candidates.length === 0 ? (
            <div className="empty">
              No candidates found. Paste the source URL on the left, or search again.
            </div>
          ) : (
            <div className="candidates">
              {current.candidates.map((candidate, index) => (
                <button
                  key={candidate.id}
                  className="card candidate"
                  disabled={busy}
                  onClick={() => confirm(candidate.source_url)}
                >
                  <span
                    className="thumb"
                    style={
                      candidate.cover_url
                        ? { backgroundImage: `url(${candidate.cover_url})` }
                        : undefined
                    }
                  />
                  <span style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <span className="title">
                      {index < 9 && <span className="kbd">{index + 1}</span>} {candidate.title}
                    </span>
                    <span className="meta">
                      <span className="pill">{candidate.source_site}</span>
                      {candidate.year && <span>{candidate.year}</span>}
                      {candidate.chapter_count && <span>{candidate.chapter_count} ch</span>}
                      <span>{Math.round(candidate.score * 100)}% match</span>
                    </span>
                  </span>
                </button>
              ))}
            </div>
          )}
        </section>
      </div>
    </>
  )
}
