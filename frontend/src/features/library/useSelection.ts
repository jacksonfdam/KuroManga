import { useCallback, useEffect, useMemo, useState } from 'react'

const STORE_KEY = 'library:selection'

/**
 * A selection is a sitting's work, so it is kept where the review screen keeps
 * its deferrals: in the browser session.
 *
 * Marking six titles and opening one of them to check what it is used to cost
 * all six, because the library unmounts on the way to a series — and checking
 * a title before acting on it is the ordinary reason to leave. `sessionStorage`
 * rather than `localStorage` for the same reason `review:skipped` is: a
 * selection nobody remembers making is one a bulk action should not be able to
 * find next week.
 *
 * Every accessor is guarded. A private window, or site data cleared
 * mid-session, throws on read and on write, and a screen that cannot remember
 * a selection must still let the user make one.
 */
function readSelection(): ReadonlySet<number> {
  try {
    const stored: unknown = JSON.parse(sessionStorage.getItem(STORE_KEY) ?? '[]')
    return new Set(
      Array.isArray(stored) ? stored.filter((id): id is number => typeof id === 'number') : [],
    )
  } catch {
    return new Set()
  }
}

function writeSelection(ids: number[]): void {
  try {
    sessionStorage.setItem(STORE_KEY, JSON.stringify(ids))
  } catch {
    // Nothing to tell the user: the selection still works for this screen, it
    // just will not survive the next load.
  }
}

/**
 * Which series the user has marked, and the bulk apply that acts on them.
 *
 * The set is kept rather than a flag per row so filtering and searching do not
 * lose a selection: the user picks three titles, narrows the list to find a
 * fourth, and the first three are still marked when they widen it again.
 */
export function useSelection() {
  const [selected, setSelected] = useState<ReadonlySet<number>>(readSelection)

  // Written from an effect rather than from inside each updater, because an
  // updater is called speculatively and must stay free of side effects.
  useEffect(() => {
    writeSelection([...selected])
  }, [selected])

  const toggle = useCallback((id: number) => {
    setSelected((held) => {
      const next = new Set(held)
      if (!next.delete(id)) next.add(id)
      return next
    })
  }, [])

  const clear = useCallback(() => setSelected(new Set()), [])

  const selectAll = useCallback((ids: number[]) => {
    setSelected(new Set(ids))
  }, [])

  /**
   * Drop marks on series the library no longer holds.
   *
   * A restored selection describes the library as it was when the tab was
   * opened, and a series can leave it — answered in Review, removed from a
   * list, dropped by a sync. Carrying that id forward would put a count on the
   * action bar larger than anything it could act on, and `review:skipped`
   * already learned the same lesson: the ids that survive are the ids still on
   * screen.
   *
   * Returns the set unchanged when nothing was dropped, so a caller may run
   * this on every load without setting state it did not change.
   */
  const retain = useCallback((known: Iterable<number>) => {
    setSelected((held) => {
      if (held.size === 0) return held
      const lives = new Set(known)
      const kept = [...held].filter((id) => lives.has(id))
      return kept.length === held.size ? held : new Set(kept)
    })
  }, [])

  const ids = useMemo(() => [...selected], [selected])

  return { selected, ids, count: selected.size, toggle, clear, selectAll, retain }
}
