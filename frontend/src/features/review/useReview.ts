import { useCallback, useEffect, useMemo, useState } from 'react'

import { api, type ReviewPayload, type ReviewQueueItem } from '../../lib/api'
import { useAsyncData } from '../../lib/useAsyncData'
import { useNotice } from '../../lib/useNotice'
import { useUrlNumber, useUrlState } from '../../lib/useUrlState'
import { arrange, readSkipped, writeSkipped } from './queue'

/** Which of the three things this screen is: the one in front of you, the list
    of what is coming, or the list of what you told it to stop asking about. */
export type ReviewView = 'reviewing' | 'queue' | 'ignored'

const REVIEW_VIEWS: readonly ReviewView[] = ['reviewing', 'queue', 'ignored']

interface Lists {
  queue: ReviewQueueItem[]
  ignored: ReviewQueueItem[]
}

/**
 * The mapping queue. This screen is the pipeline's only manual step, so it is
 * built to be cleared quickly — and, since one title no source carries used to
 * sit at the front of it and stop the other hundred and sixty-seven, to always
 * have a way forward. Three of them: confirm, skip, not interested.
 *
 * The queue and the series being reviewed are two requests, not one. They used
 * to be a single unit because splitting them had left the screen unable to tell
 * a failed load from an empty queue — that reason still stands, and is met
 * differently here: "Nothing waiting" is rendered only from a *loaded* queue of
 * length zero, and a candidate list that failed is reported over a series panel
 * the queue row itself can fill. The alternative, re-fetching the whole queue
 * on every press of Next, would blank the screen between two neighbours.
 */
export function useReview(onResolved: () => void) {
  // Tab and cursor are addressed: leaving the queue to look something up used
  // to return the screen to the first entry of the first tab.
  const [view, setView] = useUrlState<ReviewView>('tab', 'reviewing', REVIEW_VIEWS)
  const [skipped, setSkipped] = useState<number[]>(readSkipped)
  const [cursor, setCursor] = useUrlNumber('at', 0)
  const [manualUrl, setManualUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [undo, setUndo] = useState<(() => void) | null>(null)
  const { notice, report, reportFailure, clear } = useNotice()

  const loadLists = useCallback(async (): Promise<Lists> => {
    const [queue, ignored] = await Promise.all([api.reviewQueue(), api.reviewIgnored()])
    return { queue: queue.items, ignored: ignored.items }
  }, [])

  const lists = useAsyncData(loadLists)
  const order = useMemo(() => arrange(lists.data?.queue ?? [], skipped), [lists.data, skipped])

  // Derived, never stored — the address carries the cursor, not this. The queue
  // shrinks under the cursor every time a series is answered, so the number
  // that survives a reload has to be clamped against the queue as it is now:
  // otherwise a returning link points past the end of it, or at a different
  // series than the one it was written for.
  const position = order.length === 0 ? 0 : Math.min(cursor, order.length - 1)
  const at = order[position] ?? null
  const seriesId = at?.id ?? null

  const loadCurrent = useCallback(
    async (): Promise<ReviewPayload | null> =>
      seriesId === null ? null : await api.candidates(seriesId),
    [seriesId],
  )
  const detail = useAsyncData(loadCurrent)

  const settle = useCallback(() => {
    clear()
    setUndo(null)
  }, [clear])

  const goTo = useCallback(
    (index: number) => {
      setCursor(index)
      setView('reviewing')
      settle()
    },
    [setCursor, settle, setView],
  )

  const next = useCallback(() => {
    setCursor(Math.min(position + 1, order.length - 1))
    settle()
  }, [order.length, position, setCursor, settle])

  const previous = useCallback(() => {
    setCursor(Math.max(position - 1, 0))
    settle()
  }, [position, setCursor, settle])

  const confirm = useCallback(
    async (sourceUrl: string) => {
      if (!at || !sourceUrl) return
      setBusy(true)
      settle()
      try {
        await api.confirmMapping(at.id, sourceUrl)
        setManualUrl('')
        onResolved()
        // The cursor stays where it is: the answered series leaves the queue
        // and the next one takes its place, which is what makes confirming
        // nine of these in a row feel like one motion.
        lists.reload()
      } catch (failure) {
        reportFailure(failure)
      } finally {
        setBusy(false)
      }
    },
    [at, lists, onResolved, reportFailure, settle],
  )

  const skip = useCallback(() => {
    if (!at || order.length < 2) return
    const was = skipped
    const here = position
    const moved = [...skipped.filter((id) => id !== at.id), at.id]
    setSkipped(moved)
    writeSkipped(moved)
    // Moving the last series to the end leaves it exactly where it was, and a
    // button that sometimes does nothing is a button nobody trusts. From the
    // back of the queue, skipping returns to the front.
    if (here === order.length - 1) setCursor(0)
    report(`${at.title} moved to the end of the queue. It comes back before you are done.`)
    setUndo(() => () => {
      setSkipped(was)
      writeSkipped(was)
      setCursor(here)
      clear()
    })
  }, [at, clear, order.length, position, report, setCursor, skipped])

  const unignore = useCallback(
    async (series: ReviewQueueItem) => {
      setBusy(true)
      settle()
      try {
        await api.unignoreInReview(series.id)
        // A series skipped before it was ignored must not come back deferred:
        // the user has just asked for it, so it belongs in its own place.
        const kept = skipped.filter((id) => id !== series.id)
        setSkipped(kept)
        writeSkipped(kept)
        report(`${series.title} is back in the queue.`)
        onResolved()
        lists.reload()
      } catch (failure) {
        reportFailure(failure)
      } finally {
        setBusy(false)
      }
    },
    [lists, onResolved, report, reportFailure, settle, skipped],
  )

  const ignore = useCallback(async () => {
    if (!at) return
    const series = at
    setBusy(true)
    settle()
    try {
      await api.ignoreInReview(series.id)
      report(
        `${series.title} is out of the review queue. It stays in your library and on your lists — Ignored has it if you change your mind.`,
      )
      // Permanent has to mean recoverable, or it is a button nobody presses.
      // Offered here as well as on the Ignored tab, because this is the moment
      // a mis-click is still in the user's head.
      setUndo(() => () => void unignore(series))
      onResolved()
      lists.reload()
    } catch (failure) {
      reportFailure(failure)
    } finally {
      setBusy(false)
    }
  }, [at, lists, onResolved, report, reportFailure, settle, unignore])

  // Keys, and the two rules that keep them from firing by accident.
  //
  // 1-9 confirm a visible candidate without reaching for the mouse. A wrong
  // match here costs every future chapter of that series, so the shortcut calls
  // the same `confirm` a click would rather than a shortened path.
  //
  // Skip and ignore are chords, not bare letters: they share a keyboard with a
  // digit row that is already live, and `i` next to `1` is one slip away from
  // taking a series out of the queue. Shift cannot be produced by a stray digit
  // and is not a key anyone rests on. Nothing fires at all while the caret is
  // in the URL field — which is where typing a mangadex.org/title/9 used to
  // confirm candidate nine.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (view !== 'reviewing' || busy) return
      if (event.ctrlKey || event.metaKey || event.altKey) return
      const target = event.target as HTMLElement | null
      if (
        target &&
        (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))
      ) {
        return
      }
      if (event.shiftKey) {
        const key = event.key.toLowerCase()
        if (key === 's') {
          event.preventDefault()
          skip()
        } else if (key === 'i') {
          event.preventDefault()
          void ignore()
        }
        return
      }
      const candidates = detail.data?.candidates
      if (!candidates) return
      const index = Number(event.key)
      if (index >= 1 && index <= 9 && candidates[index - 1]) {
        void confirm(candidates[index - 1].source_url)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [busy, confirm, detail.data, ignore, skip, view])

  const search = useCallback(() => {
    if (!at) return
    api
      .research(at.id)
      .then(() => report('Searching this title again — candidates land here when the job finishes.'))
      .catch(reportFailure)
  }, [at, report, reportFailure])

  const changeView = useCallback(
    (to: ReviewView) => {
      setView(to)
      settle()
    },
    [setView, settle],
  )

  return {
    view,
    setView: changeView,
    order,
    ignored: lists.data?.ignored ?? [],
    skipped: useMemo(() => new Set(skipped), [skipped]),
    position,
    at,
    current: detail.data ?? null,
    // The queue is what decides whether this screen has anything to show at
    // all; the candidates are a detail of one row in it.
    loaded: lists.data !== null,
    candidatesLoaded: detail.data !== null,
    error: lists.error,
    candidatesError: detail.error,
    reload: lists.reload,
    reloadCandidates: detail.reload,
    notice,
    undo,
    manualUrl,
    setManualUrl,
    busy,
    confirm,
    skip,
    ignore,
    unignore,
    goTo,
    next,
    previous,
    search,
  }
}
