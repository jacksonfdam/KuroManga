import { useCallback, useEffect, useState } from 'react'

import { api, type ReviewPayload, type Series } from '../../lib/api'
import { useAsyncData } from '../../lib/useAsyncData'
import { useNotice } from '../../lib/useNotice'

interface Queue {
  waiting: Series[]
  current: ReviewPayload | null
}

/**
 * The mapping queue. This screen is the pipeline's only manual step, so it is
 * built to be cleared quickly: confirm advances straight to the next series.
 */
export function useReview(onResolved: () => void) {
  const [manualUrl, setManualUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const { notice, report, reportFailure, clear } = useNotice()

  // The queue and the series being reviewed load as one unit. Split across two
  // states, a failure between them left the screen with no series and no way
  // to tell that apart from an empty queue.
  const load = useCallback(async (): Promise<Queue> => {
    const waiting = await api.series('needs_review')
    return {
      waiting,
      current: waiting.length > 0 ? await api.candidates(waiting[0].id) : null,
    }
  }, [])

  const { data, error, reload } = useAsyncData(load)

  const confirm = useCallback(
    async (sourceUrl: string) => {
      const current = data?.current
      if (!current || !sourceUrl) return
      setBusy(true)
      clear()
      try {
        await api.confirmMapping(current.series.id, sourceUrl)
        setManualUrl('')
        onResolved()
        reload()
      } catch (failure) {
        reportFailure(failure)
      } finally {
        setBusy(false)
      }
    },
    [clear, data, onResolved, reload, reportFailure],
  )

  // 1-9 confirm a visible candidate without reaching for the mouse. The queue
  // is meant to move fast, but a wrong match here still costs every future
  // chapter of that series, so the shortcut calls the same `confirm` a click
  // would rather than a shortened path.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const candidates = data?.current?.candidates
      if (!candidates || busy) return
      const index = Number(event.key)
      if (index >= 1 && index <= 9 && candidates[index - 1]) {
        confirm(candidates[index - 1].source_url)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [busy, confirm, data])

  const search = useCallback(() => {
    const current = data?.current
    if (!current) return
    api
      .research(current.series.id)
      .then(() => report('Searching this title again — candidates land here when the job finishes.'))
      .catch(reportFailure)
  }, [data, report, reportFailure])

  return {
    waiting: data?.waiting ?? [],
    current: data?.current ?? null,
    loaded: data !== null,
    error,
    reload,
    notice,
    manualUrl,
    setManualUrl,
    busy,
    confirm,
    search,
  }
}
