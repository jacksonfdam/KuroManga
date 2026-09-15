import { useCallback, useMemo } from 'react'

import { api, type Series } from '../../lib/api'
import { STATUS_ORDER, type ListStatus } from '../../lib/format'
import { useAsyncData } from '../../lib/useAsyncData'
import { useUrlState } from '../../lib/useUrlState'
import { useJobEvents } from '../../lib/useEvents'
import { useNotice } from '../../lib/useNotice'
import { useQueuedProgress } from '../../lib/queuedProgress'

export type View = 'grid' | 'table'

// What the two addressable controls accept. Both lists exist so a value typed
// into the query string, or arriving from a link written against an older
// build, falls back to the default instead of reaching a screen with no branch
// for it.
const VIEWS: readonly View[] = ['grid', 'table']
const STATUS_TABS: readonly (ListStatus | 'all')[] = [...STATUS_ORDER, 'all']

// total_chapters is the provider's static count and is frequently null;
// known is what chapter_discover has actually seen on the source. Either can
// be the only number we have, so the display total falls back between them
// rather than assuming one is always populated.
export function totalChapters(series: Series): number | null {
  return series.total_chapters || series.known || null
}

export function useLibrary() {
  const load = useCallback(() => api.series(), [])
  const { data, error, reload } = useAsyncData(load)
  // The three controls this screen owns, held in the address rather than in
  // component state: opening a series unmounts the library, and rebuilding
  // these from their defaults on the way back is what lost the user's place.
  const [status, setStatus] = useUrlState<ListStatus | 'all'>('status', 'reading', STATUS_TABS)
  const [view, setView] = useUrlState<View>('view', 'grid', VIEWS)
  // Widened deliberately: an empty default would otherwise infer the literal
  // type `""`, and the filter accepts any string.
  const [query, setQuery] = useUrlState<string>('q', '')
  const { notice, reportFailure, clear } = useNotice()
  const { awaiting, queue, drop } = useQueuedProgress()

  // POST /progress only queues the write; the number the library reads comes
  // from list_entry, which the handler updates when the job runs. So the card
  // keeps showing the queued chapter over whatever the reload returns until
  // the job that actually reached the provider has moved it.
  useJobEvents((event) => {
    if (event.event !== 'job.progress') reload()
  })

  // Rows as the user's clicks left them: the stored chapter, raised by any
  // write the queue has taken and not yet written. One place rather than at
  // each of the four controls, so the card, the table row and the hero row
  // cannot disagree about what a series is on.
  const all = useMemo(
    () =>
      (data ?? []).map((row) => {
        const chapter = awaiting(row.id, row.progress)
        return chapter === null ? row : { ...row, progress: chapter }
      }),
    [data, awaiting],
  )

  // Which of those rows is still waiting. Derived from the same overlay, so a
  // row can never show a raised chapter without the marker that says why.
  const pending = useMemo(
    () => new Set((data ?? []).filter((row) => awaiting(row.id, row.progress) !== null).map((row) => row.id)),
    [data, awaiting],
  )

  /**
   * Apply, then confirm. A refused write drops the queued chapter visibly:
   * silently reverting reads as the click having missed.
   */
  const increment = useCallback(
    async (id: number, next: number) => {
      clear()
      // The title travels with the queued chapter: a write can be refused
      // while the user is on another screen, and the shell that reports it
      // has no list of its own to look the series up in.
      queue(id, next, (data ?? []).find((row) => row.id === id)?.title ?? `series ${id}`)
      try {
        await api.setProgress(id, next)
      } catch (failure) {
        drop(id)
        // The 400ms red flash says the click was refused; it cannot say why.
        // The refusals this can hit are a chapter past what the series is
        // known to have and a number that would move a list backwards, and
        // both read as the button being broken unless the reason is shown.
        reportFailure(failure)
        throw failure
      }
    },
    [clear, data, drop, queue, reportFailure],
  )

  const visible = useMemo(
    () =>
      all.filter((row) => {
        const matchesStatus = status === 'all' || row.status === status
        const matchesQuery = !query || row.title.toLowerCase().includes(query.toLowerCase())
        return matchesStatus && matchesQuery
      }),
    [all, status, query],
  )

  // Independent of the active status tab: a series still belongs here the
  // instant it drops out of "reading" from a click, not only while filtered in.
  const continueReading = useMemo(
    () =>
      [...all]
        .filter((row) => row.status === 'reading' && row.updated_at)
        .sort((a, b) => new Date(b.updated_at as string).getTime() - new Date(a.updated_at as string).getTime())
        .slice(0, 3),
    [all],
  )

  return {
    series: visible,
    all,
    loaded: data !== null,
    error,
    status,
    setStatus,
    view,
    setView,
    query,
    setQuery,
    increment,
    reload,
    continueReading,
    pending,
    notice,
  }
}
