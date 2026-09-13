import { useState } from 'react'

/**
 * Shared by every control that calls `increment`: the grid's glass overlay
 * and the table's inline stepper both need the same await-then-flash
 * behaviour, and a second copy of it is how one of them quietly lost the
 * rejection flash.
 */
export type FlashState = 'success' | 'error' | null

export function useIncrementFlash(onIncrement: (next: number) => Promise<void>) {
  const [flash, setFlash] = useState<FlashState>(null)
  const [busy, setBusy] = useState(false)

  const trigger = async (next: number) => {
    if (busy) return
    setBusy(true)
    try {
      await onIncrement(next)
      setFlash('success')
    } catch {
      setFlash('error')
    } finally {
      setBusy(false)
      setTimeout(() => setFlash(null), 400)
    }
  }

  return { flash, busy, trigger }
}
