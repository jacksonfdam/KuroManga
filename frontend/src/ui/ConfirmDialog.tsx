import { useEffect, useId, useRef, type ReactNode } from 'react'

import { Button } from './Button'
import { useScrollLock } from './useScrollLock'

/**
 * The question asked before anything is destroyed.
 *
 * Unlike `DetailPanel`, this one really is modal and behaves like it: focus
 * moves inside, Tab stays inside, and the page underneath is held still. The
 * panel deliberately does none of that, because it sits beside a list the user
 * is still working through; a dialog that is asking whether to delete
 * something is the only thing on screen that matters.
 *
 * `consequences` is a list rather than a sentence on purpose. "Are you sure?"
 * asks the user to remember what happens; naming each effect means they do not
 * have to.
 */
export function ConfirmDialog({
  title,
  consequences,
  confirmLabel,
  busy = false,
  onConfirm,
  onCancel,
  children,
}: {
  title: string
  /** What will actually happen, one effect per line. */
  consequences: string[]
  confirmLabel: string
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
  /** Anything extra the decision needs — a note, a list of what was selected. */
  children?: ReactNode
}) {
  const headingId = useId()
  const dialog = useRef<HTMLDivElement>(null)
  const cancel = useRef<HTMLButtonElement>(null)
  useScrollLock(true)

  useEffect(() => {
    // Cancel takes focus, not confirm. A destructive button under a stray
    // Enter is the accident this dialog exists to prevent.
    cancel.current?.focus()
  }, [])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onCancel()
        return
      }
      if (event.key !== 'Tab' || !dialog.current) return
      const focusable = dialog.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
      )
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      // Tab off either end wraps rather than escaping to the page behind,
      // which is still there and still full of things that change data.
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onCancel])

  return (
    <>
      <div
        aria-hidden
        onClick={onCancel}
        className="fixed inset-0 z-40 bg-surface-container-lowest/70 backdrop-blur-sm"
      />
      <div
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby={headingId}
        className="fixed left-1/2 top-1/2 z-50 w-[min(28rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-xl bg-surface-container p-space-lg shadow-overlay"
      >
        <h2 id={headingId} className="text-headline-sm text-on-surface">
          {title}
        </h2>

        <ul className="mt-space-md flex flex-col gap-space-xs">
          {consequences.map((line) => (
            <li key={line} className="flex gap-space-sm text-body-sm text-on-surface-variant">
              <span aria-hidden className="text-outline">
                •
              </span>
              <span>{line}</span>
            </li>
          ))}
        </ul>

        {children && <div className="mt-space-md">{children}</div>}

        <div className="mt-space-lg flex justify-end gap-space-sm">
          <button
            ref={cancel}
            type="button"
            onClick={onCancel}
            className="rounded-lg px-space-md py-space-sm text-body-sm text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-on-surface"
          >
            Cancel
          </button>
          <Button variant="danger" disabled={busy} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </>
  )
}
