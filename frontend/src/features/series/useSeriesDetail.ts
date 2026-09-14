import { useCallback, useMemo, useState } from 'react'

import { api, messageOf, type SeriesDetail } from '../../lib/api'
import type { ListStatus } from '../../lib/format'
import { useAsyncData } from '../../lib/useAsyncData'
import { useJobEvents } from '../../lib/useEvents'
import { useQueuedProgress } from '../../lib/queuedProgress'

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
        // Only if the updater above actually ran: rolling back to null would
        // put the screen into its first-load skeleton over a refused toggle.
        if (previous) setData(previous)
        throw failure
      }
    },
    [id, setData],
  )

  // Progress is not like the two writes around it. A status or an auto-download
  // toggle is stored on the spot; a chapter is only *queued*, and this screen
  // used to write it into the loaded detail and never look again — showing a
  // number the providers may never have received. So the accepted chapter is
  // held beside the data instead, the stream below reconciles it, and the
  // screen says which of the two it is showing.
  const [refusal, setRefusal] = useState<string | null>(null)
  const { awaiting, queue, drop } = useQueuedProgress()

  // The detail screen had no subscription at all, so a queued chapter had no
  // way to become a written one short of a manual refresh.
  useJobEvents((event) => {
    if (event.event !== 'job.progress' && event.series_id === id) reload()
  })

  const setProgress = useCallback(
    async (next: number) => {
      setRefusal(null)
      queue(id, next, detail?.series.title ?? `series ${id}`)
      try {
        await api.setProgress(id, next)
      } catch (failure) {
        drop(id)
        // The stepper's own flash says the click was refused but not why, and
        // this screen has no notice channel of its own for it.
        setRefusal(messageOf(failure))
        throw failure
      }
    },
    [detail, drop, id, queue],
  )

  const setListStatus = useCallback(
    async (status: ListStatus) => {
      let previous: SeriesDetail | null = null
      setData((current) => {
        previous = current
        return current
          ? { ...current, series: { ...current.series, status } }
          : current
      })
      try {
        await api.setListStatus(id, status)
      } catch (failure) {
        if (previous) setData(previous)
        throw failure
      }
    },
    [id, setData],
  )

  // Optimistic like the other two writes, but the note lands on a provider
  // through a job — so what is shown is "queued", and the value the provider
  // actually kept comes back with the next list_sync.
  const saveNotes = useCallback(
    async (notes: string, tags: string[]) => {
      let previous: SeriesDetail | null = null
      setData((current) => {
        previous = current
        return current
          ? { ...current, metadata: { ...current.metadata, notes, user_tags: tags } }
          : current
      })
      try {
        await api.saveNotes(id, notes, tags)
      } catch (failure) {
        if (previous) setData(previous)
        throw failure
      }
    },
    [id, setData],
  )

  const download = useCallback((from?: number, to?: number) => api.download(id, from, to), [id])
  const research = useCallback(() => api.research(id), [id])

  // The chapter still travelling to the providers, or null once the reload has
  // brought the written one back up to it.
  const queuedChapter = detail === null ? null : awaiting(id, detail.series.progress)

  // What the screen renders: the stored detail with the queued chapter over it,
  // so the stepper counts on from where the user left it rather than from the
  // number the worker has not reached yet.
  const shown = useMemo(
    () =>
      detail === null || queuedChapter === null
        ? detail
        : { ...detail, series: { ...detail.series, progress: queuedChapter } },
    [detail, queuedChapter],
  )

  return {
    detail: shown,
    queuedChapter,
    refusal,
    notFound,
    error,
    reload,
    toggleAutoDownload,
    setProgress,
    setListStatus,
    saveNotes,
    download,
    research,
  }
}
