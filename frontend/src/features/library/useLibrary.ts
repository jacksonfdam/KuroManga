import { useCallback, useEffect, useMemo, useState } from 'react'

import { api, type Series } from '../../lib/api'
import type { ListStatus } from '../../lib/format'

export type View = 'grid' | 'table'

// total_chapters is the provider's static count and is frequently null;
// known is what chapter_discover has actually seen on the source. Either can
// be the only number we have, so the display total falls back between them
// rather than assuming one is always populated.
export function totalChapters(series: Series): number | null {
  return series.total_chapters || series.known || null
}

export function useLibrary() {
  const [series, setSeries] = useState<Series[]>([])
  const [status, setStatus] = useState<ListStatus | 'all'>('reading')
  const [view, setView] = useState<View>('grid')
  const [query, setQuery] = useState('')

  const load = useCallback(() => {
    api.series().then(setSeries).catch(() => undefined)
  }, [])

  useEffect(load, [load])

  /**
   * Apply, then confirm. A rejected write restores the previous number
   * visibly: silently reverting reads as the click having missed.
   */
  const increment = useCallback(async (id: number, next: number) => {
    // The functional-updater form re-reads state at rollback time. Capturing
    // `series` in this closure would restore whatever list existed when the
    // click happened, discarding any refresh that landed while the request
    // was in flight.
    let previous: Series[] = []
    setSeries((rows) => {
      previous = rows
      return rows.map((row) => (row.id === id ? { ...row, progress: next } : row))
    })
    try {
      await api.setProgress(id, next)
    } catch (error) {
      setSeries(previous)
      throw error
    }
  }, [])

  const visible = series.filter((row) => {
    const matchesStatus = status === 'all' || row.status === status
    const matchesQuery = !query || row.title.toLowerCase().includes(query.toLowerCase())
    return matchesStatus && matchesQuery
  })

  // Independent of the active status tab: a series still belongs here the
  // instant it drops out of "reading" from a click, not only while filtered in.
  const continueReading = useMemo(
    () =>
      [...series]
        .filter((row) => row.status === 'reading' && row.updated_at)
        .sort((a, b) => new Date(b.updated_at as string).getTime() - new Date(a.updated_at as string).getTime())
        .slice(0, 3),
    [series],
  )

  return {
    series: visible,
    all: series,
    status,
    setStatus,
    view,
    setView,
    query,
    setQuery,
    increment,
    reload: load,
    continueReading,
  }
}
