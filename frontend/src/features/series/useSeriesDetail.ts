import { useCallback } from 'react'

import { api, type SeriesDetail } from '../../lib/api'
import { useAsyncData } from '../../lib/useAsyncData'

// total_chapters is the provider's static count and is frequently null; known
// is what chapter_discover has actually seen on the source. Duplicated from
// useLibrary's identical helper rather than imported — feature folders never
// import from each other.
export function totalChapters(detail: SeriesDetail): number | null {
  return detail.series.total_chapters || detail.series.known || null
}

export function useSeriesDetail(id: number) {
  const load = useCallback(() => api.seriesDetail(id), [id])
  const { data: detail, error, notFound, reload, setData } = useAsyncData(load)

  // Apply, then confirm — the same rollback-on-rejection shape useIncrementFlash
  // uses for progress, so a refused toggle visibly reverts instead of silently
  // leaving the switch in a state the server never accepted.
  const toggleAutoDownload = useCallback(
    async (enabled: boolean) => {
      let previous: SeriesDetail | null = null
      setData((current) => {
        previous = current
        return current ? { ...current, series: { ...current.series, auto_download: enabled } } : current
      })
      try {
        await api.setAutoDownload(id, enabled)
      } catch (failure) {
        setData(previous)
        throw failure
      }
    },
    [id, setData],
  )

  const download = useCallback((from?: number, to?: number) => api.download(id, from, to), [id])
  const research = useCallback(() => api.research(id), [id])

  return { detail, notFound, error, reload, toggleAutoDownload, download, research }
}
