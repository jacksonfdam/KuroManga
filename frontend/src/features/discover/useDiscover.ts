import { useCallback, useMemo } from 'react'

import { api, type DiscoverItem, type DiscoverKind, type DiscoverSort } from '../../lib/api'
import { useAsyncData } from '../../lib/useAsyncData'
import { useDebounced } from '../../lib/useDebounced'
import { useJobEvents } from '../../lib/useEvents'
import { useNotice } from '../../lib/useNotice'
import { useUrlNumber, useUrlPatch, useUrlState } from '../../lib/useUrlState'

export const PER_CHOICES = [20, 50, 100] as const
export const DEFAULT_PER = 50

// Both lists exist so a value typed into the query string, or arriving from a
// link written against an older build, falls back to the default instead of
// reaching a screen with no branch for it.
const SORTS: readonly DiscoverSort[] = ['rank', 'title', '-title', 'added', '-added']
const KINDS: readonly DiscoverKind[] = ['suggestion', 'review', 'unmatched']

const DEFAULTS = { q: '', kind: '', sort: 'rank', page: 1, per: DEFAULT_PER }

export function useDiscover() {
  // Every control rides in the address: opening an item unmounts the screen,
  // and rebuilding these from their defaults on the way back is what lost the
  // user's place.
  const [query] = useUrlState<string>('q', '')
  const [kindParam] = useUrlState<string>('kind', '')
  const [sort] = useUrlState<DiscoverSort>('sort', 'rank', SORTS)
  const [page] = useUrlNumber('page', 1)
  const [perParam] = useUrlNumber('per', DEFAULT_PER)
  const per = (PER_CHOICES as readonly number[]).includes(perParam) ? perParam : DEFAULT_PER

  const kinds = useMemo(
    () => kindParam.split(',').filter((k): k is DiscoverKind => KINDS.includes(k as DiscoverKind)),
    [kindParam],
  )

  // Two setters called from one handler lose one of the writes — each
  // navigation replaces the address rather than amending it. Every control
  // here also resets the page, so every one of them changes two parameters and
  // none of them may use a single-key setter.
  const patch = useUrlPatch(DEFAULTS)
  const { notice, report, reportFailure } = useNotice()

  // The field and the address follow every keystroke; the request waits. Eight
  // characters typed into a feed that reads three tables is otherwise eight
  // reads of all of them.
  const settled = useDebounced(query, 250)

  const load = useCallback(
    () => api.discover({ q: settled, kinds, sort, page, per }),
    [settled, kinds, sort, page, per],
  )
  const { data, error, reload } = useAsyncData(load)

  // Answering an item enqueues work, and the job stream is what says the answer
  // landed. Progress ticks are ignored: they fire continuously and change
  // nothing about which items are still waiting.
  useJobEvents((event) => {
    if (event.event !== 'job.progress') reload()
  })

  // Written straight to the address, so the field follows every keystroke; it
  // is only the request that waits. A new search also means page one, which is
  // why this goes through the patch like every other control here.
  const setQuery = useCallback((next: string) => patch({ q: next, page: 1 }), [patch])

  /** Chips are a set, not a choice: two selected means both, none means all. */
  const toggleKind = useCallback(
    (kind: DiscoverKind) => {
      const next = kinds.includes(kind) ? kinds.filter((k) => k !== kind) : [...kinds, kind]
      patch({ kind: next.join(','), page: 1 })
    },
    [kinds, patch],
  )

  const setSort = useCallback((next: DiscoverSort) => patch({ sort: next, page: 1 }), [patch])
  // A page size change moves every boundary, so the page it would land on means
  // nothing. Back to the first.
  const setPer = useCallback((next: number) => patch({ per: next, page: 1 }), [patch])
  const setPage = useCallback((next: number) => patch({ page: next }), [patch])

  /**
   * Stop asking about this one.
   *
   * Written to whichever of the three stores the item came from. Unifying that
   * storage is a migration the design deliberately leaves out: one action over
   * three stores is a seam worth accepting, and nothing about this screen
   * requires converting three histories into one.
   */
  const dismiss = useCallback(
    (item: DiscoverItem) => {
      const call =
        item.kind === 'suggestion'
          ? api.dismissSuggestion(item.id)
          : item.kind === 'review'
            ? api.ignoreInReview(item.id)
            : api.hideUnmatched(item.id)
      call
        .then(() => {
          report(`${item.title} won't be suggested again.`)
          return reload()
        })
        .catch(reportFailure)
    },
    [reload, report, reportFailure],
  )

  return {
    items: data?.items ?? [],
    total: data?.total ?? 0,
    actionable: data?.actionable ?? 0,
    pages: data?.pages ?? 1,
    loaded: data !== null,
    error,
    reload,
    notice,
    dismiss,
    query,
    setQuery,
    kinds,
    toggleKind,
    sort,
    setSort,
    page,
    setPage,
    per,
    setPer,
  }
}
