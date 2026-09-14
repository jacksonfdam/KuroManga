import { useEffect, useId, useState, type ReactNode } from 'react'

import { Icon } from './Icon'
import { useScrollLock } from './useScrollLock'

// Tailwind's `lg`, which is where the panel stops being a sheet and becomes a
// column. The classes below and this query have to name the same breakpoint:
// locking the page while the panel is a sticky column would freeze a page the
// panel is scrolling with.
const SHEET = '(max-width: 1023.98px)'

/** True while the panel is rendering as a sheet rather than as a column. */
function useIsSheet(): boolean {
  const [isSheet, setIsSheet] = useState(() => window.matchMedia(SHEET).matches)

  useEffect(() => {
    const query = window.matchMedia(SHEET)
    const update = () => setIsSheet(query.matches)
    // A window dragged past lg with the panel open has to give the page back,
    // so the lock follows the breakpoint rather than only the open state.
    update()
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])

  return isSheet
}

/**
 * The detail beside a list, on two screens.
 *
 * Above lg it is a sticky column that scrolls with the page and stops below
 * the header. Below lg there is no room for a column, so the same panel is a
 * sheet over the list - one component rather than two, because two is how the
 * unmatched panel and the discovery panel would quietly stop behaving alike.
 *
 * Escape closes it, a click on the scrim closes it, and the page underneath is
 * held still while it is open. A panel that can only be dismissed by hunting
 * for a small button is the thing that makes a two-pane list feel like a trap.
 *
 * Focus is deliberately not moved into it and not trapped: above lg this is a
 * column sitting beside the list, not a modal, and a trap there would take the
 * keyboard away from the list the user is still working through. The sheet
 * form is dismissible three ways instead.
 */
export function DetailPanel({
  title,
  onClose,
  children,
}: {
  title: string
  onClose: () => void
  children: ReactNode
}) {
  const headingId = useId()
  const isSheet = useIsSheet()
  useScrollLock(isSheet)

  useEffect(() => {
    const dismiss = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', dismiss)
    return () => window.removeEventListener('keydown', dismiss)
  }, [onClose])

  return (
    <>
      {/* Sheet only: above lg the panel is a column and a scrim over the list
          beside it would be dimming the wrong thing. z-10 puts it under the
          panel and over the list, and leaves the fixed header and nav (z-50)
          alone, as the panel itself already does. */}
      <div
        aria-hidden
        onClick={onClose}
        className="fixed inset-0 z-10 bg-surface-container-lowest/60 backdrop-blur-sm lg:hidden"
      />
      <aside
        aria-labelledby={headingId}
        className="fixed inset-x-0 bottom-0 z-20 max-h-[75vh] overflow-y-auto overscroll-contain rounded-t-xl bg-surface-container p-space-lg pb-nav-clearance shadow-overlay lg:static lg:z-0 lg:max-h-[calc(100vh-8rem)] lg:overscroll-auto lg:rounded-xl lg:pb-space-lg lg:shadow-card"
      >
        <div className="mb-space-md flex items-start justify-between gap-space-sm">
          <h2 id={headingId} className="min-w-0 text-headline-sm text-on-surface">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close details"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-outline transition-colors hover:bg-surface-container-high hover:text-on-surface"
          >
            <Icon name="chevron" className="h-4 w-4 -rotate-90" />
          </button>
        </div>
        <div className="flex flex-col gap-space-md">{children}</div>
      </aside>
    </>
  )
}
