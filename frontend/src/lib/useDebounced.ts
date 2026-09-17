import { useEffect, useState } from 'react'

/**
 * The value, once it has stopped changing.
 *
 * A search box owns two different things at two different speeds. What the
 * field shows and what the address records have to follow every keystroke, or
 * the caret lags and the URL is wrong for whoever copies it. What the API is
 * asked has to wait, or typing eight characters costs eight requests against a
 * feed that reads three tables.
 *
 * So the control keeps its value and the request takes this one.
 */
export function useDebounced<T>(value: T, delayMs: number): T {
  const [settled, setSettled] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])

  return settled
}
