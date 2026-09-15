import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'

/**
 * One contract for a control the screen owns.
 *
 * Every screen used to hold its status tab, its view, its search box and its
 * page in component state. Opening a series unmounts the screen, so coming
 * back rebuilt all four from their defaults — the library returned to
 * "reading" as a grid with an empty filter, and the review queue returned to
 * its first entry. Checking a title before acting on it is the ordinary reason
 * to leave, so the state worth keeping was the state most reliably lost.
 *
 * The query string is the fix rather than a store, because it is the one place
 * that already survives: the browser restores it on Back, a reload keeps it,
 * and the address can be handed to someone else.
 *
 * A value equal to its default writes no parameter at all, so `/library` stays
 * `/library` until something is actually changed and the address never fills
 * with the state of controls nobody touched.
 *
 * Writes replace rather than push. Typing four characters into a filter is one
 * decision, not four, and pushing each would bury the screen the user was on
 * under its own keystrokes — Back has to leave the screen, not undo a letter.
 * The push that matters is the navigation away, which the link performs and
 * which captures whatever the parameters said at that moment.
 */
function write(
  setParams: ReturnType<typeof useSearchParams>[1],
  edit: (params: URLSearchParams) => void,
): void {
  setParams(
    (current) => {
      const updated = new URLSearchParams(current)
      edit(updated)
      return updated
    },
    { replace: true },
  )
}

/**
 * Several parameters, changed together, in one navigation.
 *
 * **Two of these setters called from one handler lose one of the writes.** Each
 * navigation replaces the address rather than amending it, and React Router
 * does not run one updater against what the other just wrote, so the second
 * call decides the whole query string and the first is simply gone. It fails
 * silently and only in the pairing: each setter is correct on its own, which is
 * why `setCursor(13); setView('reviewing')` moved the review screen to the
 * reviewing tab and showed the *first* series in the queue — the cursor never
 * reached the address. The unmatched screen's search box and its Hidden tab
 * broke the same way; both reset the page offset as they go, so both lost the
 * change the user had actually asked for.
 *
 * So: a handler that changes more than one parameter calls this, once. The
 * defaults are the same ones the individual hooks were given — a value equal to
 * its default writes no parameter, so the address stays clean.
 */
export function useUrlPatch(
  defaults: Record<string, string | number>,
): (patch: Record<string, string | number>) => void {
  const [, setParams] = useSearchParams()
  const serialised = JSON.stringify(defaults)

  return useCallback(
    (patch: Record<string, string | number>) => {
      const fallbacks = JSON.parse(serialised) as Record<string, string | number>
      write(setParams, (updated) => {
        for (const [key, next] of Object.entries(patch)) {
          if (next === fallbacks[key]) updated.delete(key)
          else updated.set(key, String(next))
        }
      })
    },
    // The defaults are a literal written at the call site, so a new object
    // arrives on every render; comparing their contents keeps this callback
    // stable, which matters because it lands in other hooks' dependencies.
    [serialised, setParams],
  )
}

export function useUrlState<T extends string>(
  key: string,
  fallback: T,
  /** Accepted values. A parameter outside the list reads as the default rather
      than reaching a screen that has no branch for it — the query string is
      typed by hand and arrives from old links. */
  allowed?: readonly T[],
): [T, (next: T) => void] {
  const [params, setParams] = useSearchParams()
  const raw = params.get(key)
  const value = raw !== null && (!allowed || (allowed as readonly string[]).includes(raw))
    ? (raw as T)
    : fallback

  const set = useCallback(
    (next: T) => {
      write(setParams, (updated) => {
        if (next === fallback) updated.delete(key)
        else updated.set(key, next)
      })
    },
    [fallback, key, setParams],
  )

  return [value, set]
}

/**
 * The same, for a parameter that counts: a page offset or a queue cursor.
 *
 * A value that is not a number, or is negative, reads as the default. Both
 * reach this from a hand-edited address, and a NaN offset would ask the API
 * for `offset=NaN` rather than fail anywhere the user could see it.
 */
export function useUrlNumber(key: string, fallback: number): [number, (next: number) => void] {
  const [params, setParams] = useSearchParams()
  const parsed = Number(params.get(key))
  const value = params.get(key) !== null && Number.isInteger(parsed) && parsed >= 0 ? parsed : fallback

  const set = useCallback(
    (next: number) => {
      write(setParams, (updated) => {
        if (next === fallback) updated.delete(key)
        else updated.set(key, String(next))
      })
    },
    [fallback, key, setParams],
  )

  return [value, set]
}
