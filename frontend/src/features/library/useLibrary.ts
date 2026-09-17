import { useCallback, useMemo } from 'react'

import { api, type Series } from '../../lib/api'
import { STATUS_ORDER, type ListStatus } from '../../lib/format'
import { useAsyncData } from '../../lib/useAsyncData'
import { useUrlNumber, useUrlPatch, useUrlState } from '../../lib/useUrlState'
import { useJobEvents } from '../../lib/useEvents'
import { useNotice } from '../../lib/useNotice'
import { useQueuedProgress } from '../../lib/queuedProgress'

export type View = 'grid' | 'table'
export type LibrarySort = 'title' | '-title' | '-updated' | '-progress'

export const PER_CHOICES = [20, 50, 100] as const
export const DEFAULT_PER = 50

// What the two addressable controls accept. Both lists exist so a value typed
// into the query string, or arriving from a link written against an older
// build, falls back to the default instead of reaching a screen with no branch
// for it.
const VIEWS: readonly View[] = ['grid', 'table']
const STATUS_TABS: readonly (ListStatus | 'all')[] = [...STATUS_ORDER, 'all']
const SORTS: readonly LibrarySort[] = ['title', '-title', '-updated', '-progress']

const DEFAULTS = { status: 'reading', q: '', format: '', sort: 'title', page: 1, per: DEFAULT_PER }

/**
 * One spelling per format.
 *
 * Two providers write the same word with different casing - 134 rows say
 * `MANGA` and 148 say `manga` - so grouping on the raw value puts two Manga
 * chips side by side, each holding half the library.
 */
export function formatKey(series: Series): string {
  return (series.format ?? '').toLowerCase()
}

function stamp(series: Series): number {
  // Never updated sorts last under "recently updated", the same way an undated
  // item does in Discover: zero is the bottom of a descending sort.
  return series.updated_at ? new Date(series.updated_at).getTime() : 0
}

function compare(sort: LibrarySort): (a: Series, b: Series) => number {
  if (sort === '-title') return (a, b) => b.title.localeCompare(a.title)
  if (sort === '-updated') return (a, b) => stamp(b) - stamp(a)
  if (sort === '-progress') return (a, b) => b.progress - a.progress
  return (a, b) => a.title.localeCompare(b.title)
}

export function formatLabel(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

// How long the manga is, from the two partial answers we hold.
//
// total_chapters is the provider's static count and is frequently null;
// known is what chapter_discover has actually seen on the source. Either can
// be the only number we have, and either can be the larger — so neither may
// shrink the other. A provider count goes stale the moment a chapter is
// published; discovery has only found what it has looked for so far.
export function totalChapters(series: Series): number | null {
  return Math.max(series.total_chapters ?? 0, series.known ?? 0) || null
}

export function useLibrary() {
  const load = useCallback(() => api.series(), [])
  const { data, error, reload } = useAsyncData(load)
  // The three controls this screen owns, held in the address rather than in
  // component state: opening a series unmounts the library, and rebuilding
  // these from their defaults on the way back is what lost the user's place.
  const [status] = useUrlState<ListStatus | 'all'>('status', 'reading', STATUS_TABS)
  const [view, setView] = useUrlState<View>('view', 'grid', VIEWS)
  // Widened deliberately: an empty default would otherwise infer the literal
  // type `""`, and the filter accepts any string.
  const [query] = useUrlState<string>('q', '')
  const [format] = useUrlState<string>('format', '')
  const [sort] = useUrlState<LibrarySort>('sort', 'title', SORTS)
  const [page] = useUrlNumber('page', 1)
  const [perParam] = useUrlNumber('per', DEFAULT_PER)
  const per = (PER_CHOICES as readonly number[]).includes(perParam) ? perParam : DEFAULT_PER

  // Every control but the view switcher also resets the page, so every one of
  // them writes two parameters. Two single-key setters called from one handler
  // lose one of the writes, so they all go through the patch.
  const patch = useUrlPatch(DEFAULTS)
  const setStatus = useCallback(
    (next: ListStatus | 'all') => patch({ status: next, page: 1 }),
    [patch],
  )
  const setQuery = useCallback((next: string) => patch({ q: next, page: 1 }), [patch])
  const setFormat = useCallback((next: string) => patch({ format: next, page: 1 }), [patch])
  const setSort = useCallback((next: LibrarySort) => patch({ sort: next, page: 1 }), [patch])
  // A page size change moves every boundary, so the page it would land on means
  // nothing. Back to the first.
  const setPer = useCallback((next: number) => patch({ per: next, page: 1 }), [patch])
  const setPage = useCallback((next: number) => patch({ page: next }), [patch])
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

  const visible = useMemo(() => {
    const kept = all.filter((row) => {
      const matchesStatus = status === 'all' || row.status === status
      const matchesQuery = !query || row.title.toLowerCase().includes(query.toLowerCase())
      const matchesFormat = !format || formatKey(row) === format
      return matchesStatus && matchesQuery && matchesFormat
    })
    return [...kept].sort(compare(sort))
  }, [all, status, query, format, sort])

  // Which formats the library actually holds, so the chips are the answer to a
  // question about this library rather than a fixed list most of which would
  // filter to nothing.
  const formats = useMemo(() => {
    const counts = new Map<string, number>()
    for (const row of all) {
      const key = formatKey(row)
      if (key) counts.set(key, (counts.get(key) ?? 0) + 1)
    }
    return [...counts.entries()]
      .map(([key, count]) => ({ key, label: formatLabel(key), count }))
      .sort((a, b) => b.count - a.count)
  }, [all])

  const pages = Math.max(1, Math.ceil(visible.length / per))
  // The whole library is already in hand, so a page here is a view control and
  // not a request. Slicing after the sort is what makes page 2 the second page
  // of the order the reader chose rather than of the order they arrived in.
  const paged = useMemo(() => visible.slice((page - 1) * per, page * per), [visible, page, per])

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
    series: paged,
    matching: visible.length,
    all,
    loaded: data !== null,
    error,
    status,
    setStatus,
    view,
    setView,
    query,
    setQuery,
    format,
    setFormat,
    formats,
    sort,
    setSort,
    page,
    setPage,
    pages,
    per,
    setPer,
    increment,
    reload,
    continueReading,
    pending,
    notice,
  }
}
