import { useState } from 'react'

import { Icon } from '../../ui'

// Markup reference: the `quick-plus-btn` overlay in
// .redesign/biblioteca_principal_sincronizada_com_komga_provedores/code.html.
// The 400ms flash is the only feedback a one-click control gets, so success
// and rejection have to look different rather than both reverting silently.
const FLASH: Record<'success' | 'error', string> = {
  success: 'bg-secondary text-on-secondary border-secondary',
  error: 'bg-error text-on-error border-error',
}

export function QuickIncrement({
  progress,
  onIncrement,
}: {
  progress: number
  onIncrement: (next: number) => Promise<void>
}) {
  const [flash, setFlash] = useState<'success' | 'error' | null>(null)
  const [busy, setBusy] = useState(false)

  const handleClick = async () => {
    if (busy) return
    setBusy(true)
    try {
      await onIncrement(progress + 1)
      setFlash('success')
    } catch {
      setFlash('error')
    } finally {
      setBusy(false)
      setTimeout(() => setFlash(null), 400)
    }
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={busy}
      aria-label="Mark next chapter read"
      title="Mark next chapter read"
      className={`flex h-8 w-8 items-center justify-center rounded-lg border border-white/15 bg-surface-container/85 text-on-surface backdrop-blur transition-all active:scale-90 disabled:cursor-not-allowed ${
        flash ? FLASH[flash] : 'hover:bg-primary hover:text-on-primary'
      }`}
    >
      <Icon name="add" className="h-4 w-4" />
    </button>
  )
}
