import type { ReactNode } from 'react'

import { Icon, type IconName } from './Icon'

/**
 * No mockup depicts an empty screen either, for the same reason noted in
 * Skeleton.tsx — this follows the same card/icon-tile pattern used
 * throughout the mockups for a self-contained status block.
 */
export function EmptyState({
  icon,
  title,
  detail,
  action,
}: {
  icon: IconName
  title: string
  detail: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center gap-space-sm rounded-xl bg-surface-container px-space-xl py-space-xl text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-surface-container-high text-on-surface-variant">
        <Icon name={icon} className="h-6 w-6" />
      </div>
      <h3 className="text-title-md text-on-surface">{title}</h3>
      <p className="max-w-sm text-body-sm text-on-surface-variant">{detail}</p>
      {action && <div className="mt-space-xs">{action}</div>}
    </div>
  )
}
