import { useCallback, useEffect, useState } from 'react'

import { api, type SeriesDetail } from '../../lib/api'

// total_chapters is the provider's static count and is frequently null; known
// is what chapter_discover has actually seen on the source. Duplicated from
// useLibrary's identical helper rather than imported — feature folders never
// import from each other.
export function totalChapters(detail: SeriesDetail): number | null {
  return detail.series.total_chapters || detail.series.known || null
}

export function useSeriesDetail(id: number) {
  const [detail, setDetail] = useState<SeriesDetail | null>(null)
  const [notFound, setNotFound] = useState(false)

  const load = useCallback(() => {
    api
      .seriesDetail(id)
      .then((result) => {
        setDetail(result)
        setNotFound(false)
      })
      // A stale `true` from a previous id would otherwise strand a later,
      // valid navigation (e.g. editing the URL from a bad id to a good one)
      // on the "not found" screen forever, since this route never remounts.
      .catch(() => setNotFound(true))
  }, [id])

  useEffect(load, [load])

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

  return { detail, notFound, reload: load, toggleAutoDownload, download, research }
}
