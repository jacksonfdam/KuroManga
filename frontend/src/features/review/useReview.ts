import { useCallback, useEffect, useState } from 'react'

import { api, type ReviewPayload, type Series } from '../../lib/api'

/**
 * The mapping queue. This screen is the pipeline's only manual step, so it is
 * built to be cleared quickly: confirm advances straight to the next series.
 */
export function useReview(onResolved: () => void) {
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

  // 1-9 confirm a visible candidate without reaching for the mouse. The queue
  // is meant to move fast, but a wrong match here still costs every future
  // chapter of that series, so the shortcut calls the same `confirm` a click
  // would rather than a shortened path.
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

  const search = useCallback(() => {
    if (!current) return
    api.research(current.series.id).then(() => undefined)
  }, [current])

  return { queue, current, manualUrl, setManualUrl, busy, error, confirm, search }
}
