import { useCallback, useMemo, useState } from 'react'

/**
 * Which series the user has marked, and the bulk apply that acts on them.
 *
 * The set is kept rather than a flag per row so filtering and searching do not
 * lose a selection: the user picks three titles, narrows the list to find a
 * fourth, and the first three are still marked when they widen it again.
 */
export function useSelection() {
  const [selected, setSelected] = useState<ReadonlySet<number>>(() => new Set())

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

  const ids = useMemo(() => [...selected], [selected])

  return { selected, ids, count: selected.size, toggle, clear, selectAll }
}
