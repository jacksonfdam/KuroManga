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
      setParams(
        (current) => {
          const updated = new URLSearchParams(current)
          if (next === fallback) updated.delete(key)
          else updated.set(key, next)
          return updated
        },
        { replace: true },
      )
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
      setParams(
        (current) => {
          const updated = new URLSearchParams(current)
          if (next === fallback) updated.delete(key)
          else updated.set(key, String(next))
          return updated
        },
        { replace: true },
      )
    },
    [fallback, key, setParams],
  )

  return [value, set]
}
