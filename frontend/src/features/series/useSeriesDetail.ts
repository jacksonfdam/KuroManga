import { useCallback, useEffect, useState } from 'react'

import { ApiError, api, type SeriesDetail } from '../../lib/api'

// total_chapters is the provider's static count and is frequently null; known
// is what chapter_discover has actually seen on the source. Duplicated from
// useLibrary's identical helper rather than imported — feature folders never
// import from each other.
export function totalChapters(detail: SeriesDetail): number | null {
  return detail.series.total_chapters || detail.series.known || null
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

export function useSeriesDetail(id: number) {
  const [detail, setDetail] = useState<SeriesDetail | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api
      .seriesDetail(id)
      .then((result) => {
        setDetail(result)
        setNotFound(false)
        setError(null)
      })
      .catch((err: unknown) => {
        // A 404 means the series itself is gone — that's the only case worth
        // replacing the screen for. Anything else (a dropped connection, a
        // 500) is a refresh that failed, and a failed refresh must not throw
        // away a page the user is already looking at — it only happened
        // because `load` also runs for `reload`, which every write in this
        // feature calls after a mutation succeeds.
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true)
          setError(null)
        } else {
          setError(messageOf(err))
        }
      })
  }, [id])

  useEffect(() => {
    // Reset before the new id's own fetch resolves, so switching series never
    // shows the previous one's data (or its stale not-found/error state)
    // while the new one is still in flight.
    setDetail(null)
    setNotFound(false)
    setError(null)
    load()
  }, [id, load])

  // Apply, then confirm — the same rollback-on-rejection shape useIncrementFlash
  // uses for progress, so a refused toggle visibly reverts instead of silently
  // leaving the switch in a state the server never accepted.
  const toggleAutoDownload = useCallback(
    async (enabled: boolean) => {
      if (!detail) return
      const previous = detail
      setDetail({ ...detail, series: { ...detail.series, auto_download: enabled } })
      try {
        await api.setAutoDownload(id, enabled)
      } catch (error) {
        setDetail(previous)
        throw error
      }
    },
    [detail, id],
  )

  const download = useCallback((from?: number, to?: number) => api.download(id, from, to), [id])
  const research = useCallback(() => api.research(id), [id])

  return { detail, notFound, error, reload: load, toggleAutoDownload, download, research }
}
