import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react'

import { ApiError, messageOf } from './api'

/**
 * One contract for a screen's own data.
 *
 * The five screens were built in sequence and each invented its own answer to
 * a failed request: three swallowed the rejection into an empty state that
 * told the user to go and connect a provider, one hung on "Loading…" forever,
 * and one caught the error into a variable it could never reach. A dead API
 * has to read as a dead API on every screen, so the contract lives here
 * instead of five times over.
 *
 * `data` and `error` together name the state to render:
 *
 *   data null, error null — the first request is still in flight (skeleton)
 *   data null, error set  — the first request failed, nothing to fall back to
 *   data set,  error set  — a refresh failed; what is on screen is still real
 *   data set,  error null — loaded
 *
 * `notFound` narrows the second case to a 404: the only failure that means
 * "this will never load" rather than "try again".
 */
export interface AsyncData<T> {
  data: T | null
  error: string | null
  notFound: boolean
  reload: () => void
  setData: Dispatch<SetStateAction<T | null>>
}

/**
 * `load` is the effect's only dependency, so it has to be stable — wrap it in
 * useCallback keyed on whatever the request varies by, or every render starts
 * another fetch.
 */
export function useAsyncData<T>(load: () => Promise<T>): AsyncData<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)
  const generation = useRef(0)

  const reload = useCallback(() => {
    // Two reloads can be in flight at once (a retry click over a live SSE
    // refresh); without this the slower, older answer overwrites the newer one.
    const mine = ++generation.current
    load()
      .then((result) => {
        if (generation.current !== mine) return
        setData(result)
        setError(null)
        setNotFound(false)
      })
      .catch((failure: unknown) => {
        if (generation.current !== mine) return
        // Data already on screen survives: a failed refresh must not throw
        // away a page the user is reading, which is what makes the
        // data-set/error-set state above worth distinguishing at all.
        setError(messageOf(failure))
        setNotFound(failure instanceof ApiError && failure.status === 404)
      })
  }, [load])

  useEffect(() => {
    // Reset before the new request resolves, so a screen keyed on an id never
    // shows the previous id's data (or its stale error) while the new one is
    // still loading.
    setData(null)
    setError(null)
    setNotFound(false)
    reload()
  }, [reload])

  return { data, error, notFound, reload, setData }
}
