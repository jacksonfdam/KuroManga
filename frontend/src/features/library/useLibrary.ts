import { useCallback, useMemo, useState } from 'react'

import { api, type Series } from '../../lib/api'
import type { ListStatus } from '../../lib/format'
import { useAsyncData } from '../../lib/useAsyncData'
import { useJobEvents } from '../../lib/useEvents'

export type View = 'grid' | 'table'

// total_chapters is the provider's static count and is frequently null;
// known is what chapter_discover has actually seen on the source. Either can
// be the only number we have, so the display total falls back between them
// rather than assuming one is always populated.
export function totalChapters(series: Series): number | null {
  return series.total_chapters || series.known || null
}

export function useLibrary() {
  const load = useCallback(() => api.series(), [])
  const { data, error, reload, setData } = useAsyncData(load)
  const [status, setStatus] = useState<ListStatus | 'all'>('reading')
  const [view, setView] = useState<View>('grid')
  const [query, setQuery] = useState('')

  const all = useMemo(() => data ?? [], [data])

  // POST /progress only queues the write; the number the library reads comes
  // from list_entry, which the handler updates when the job runs. So the card
  // is reconciled twice: once against the reload below, and again when the
  // job that actually reached the provider reports done.
  useJobEvents((event) => {
    if (event.event !== 'job.progress') reload()
  })

  /**
   * Apply, then confirm. A rejected write restores the previous number
   * visibly: silently reverting reads as the click having missed.
   */
  const increment = useCallback(
    async (id: number, next: number) => {
      // The functional-updater form re-reads state at rollback time. Capturing
      // `data` in this closure would restore whatever list existed when the
      // click happened, discarding any refresh that landed while the request
      // was in flight.
      let previous: Series[] = []
      setData((rows) => {
        previous = rows ?? []
        return (rows ?? []).map((row) => (row.id === id ? { ...row, progress: next } : row))
      })
      try {
        await api.setProgress(id, next)
      } catch (failure) {
        setData(previous)
        throw failure
      }
      reload()
    },
    [reload, setData],
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
  }
}
