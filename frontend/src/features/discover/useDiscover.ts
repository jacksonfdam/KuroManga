import { useCallback } from 'react'

import { api, type DiscoverItem } from '../../lib/api'
import { useAsyncData } from '../../lib/useAsyncData'
import { useJobEvents } from '../../lib/useEvents'
import { useNotice } from '../../lib/useNotice'
import { useUrlNumber } from '../../lib/useUrlState'

export const PAGE_SIZE = 40

export function useDiscover() {
  // The page rides in the address like every other view control here, so
  // opening an item and coming back does not lose your place.
  const [offset, setOffset] = useUrlNumber('offset', 0)
  const { notice, report, reportFailure } = useNotice()

  const load = useCallback(() => api.discover(PAGE_SIZE, offset), [offset])
  const { data, error, reload } = useAsyncData(load)

  // Answering an item enqueues work, and the job stream is what says the answer
  // landed. Progress ticks are ignored: they fire continuously and change
  // nothing about which items are still waiting.
  useJobEvents((event) => {
    if (event.event !== 'job.progress') reload()
  })

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
    loaded: data !== null,
    error,
    reload,
    notice,
    dismiss,
    offset,
    setOffset,
  }
}
