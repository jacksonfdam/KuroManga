import { useEffect, useId, type ReactNode } from 'react'

import { Icon } from './Icon'

/**
 * The detail beside a list, on two screens.
 *
 * Above lg it is a sticky column that scrolls with the page and stops below
 * the header. Below lg there is no room for a column, so the same panel is a
 * sheet over the list - one component rather than two, because two is how the
 * unmatched panel and the discovery panel would quietly stop behaving alike.
 *
 * Escape closes it. A panel that can only be dismissed by hunting for a small
 * button is the thing that makes a two-pane list feel like a trap.
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

  useEffect(() => {
    const dismiss = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', dismiss)
    return () => window.removeEventListener('keydown', dismiss)
  }, [onClose])

  return (
    <aside
      aria-labelledby={headingId}
      className="fixed inset-x-0 bottom-0 z-20 max-h-[75vh] overflow-y-auto rounded-t-xl bg-surface-container p-space-lg pb-nav-clearance shadow-overlay lg:static lg:z-0 lg:max-h-[calc(100vh-8rem)] lg:rounded-xl lg:pb-space-lg lg:shadow-card"
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
  )
}
