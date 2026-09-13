import type { ReactNode } from 'react'

import { STATUS_LABEL, STATUS_ORDER, type ListStatus } from '../lib/format'
import { Button } from './Button'
import { Toggle } from './Toggle'

/**
 * The two questions every "add this to my lists" decision asks: what status to
 * write, and whether to start downloading now. It lives in `ui/` rather than in
 * either screen because a suggestion and a searched-for title are the same
 * decision made from two places, and a feature folder may not import another.
 */
export function AddToList({
  status,
  download,
  disabled = false,
  busy = false,
  addLabel = 'Add',
  idPrefix,
  onStatus,
  onDownload,
  onAdd,
  children,
}: {
  status: ListStatus
  download: boolean
  disabled?: boolean
  busy?: boolean
  addLabel?: string
  /** Unique per card: the select and its label are paired by id, and a page
      renders many of these at once. */
  idPrefix: string
  onStatus: (status: ListStatus) => void
  onDownload: (download: boolean) => void
  onAdd: () => void
  children?: ReactNode
}) {
  const selectId = `${idPrefix}-status`
  return (
    <div className="flex flex-col gap-space-sm">
      <div className="flex flex-col gap-space-xs">
        <label htmlFor={selectId} className="font-mono text-label-sm text-outline">
          Status
        </label>
        <select
          id={selectId}
          value={status}
          disabled={disabled}
          onChange={(event) => onStatus(event.target.value as ListStatus)}
          className="w-full rounded-lg bg-surface-container-lowest px-space-sm py-space-xs text-body-sm text-on-surface focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-50"
        >
          {STATUS_ORDER.map((value) => (
            <option key={value} value={value}>
              {STATUS_LABEL[value]}
            </option>
          ))}
        </select>
      </div>
      <Toggle checked={download} disabled={disabled} onChange={onDownload} label="Download now" />
      <div className="flex flex-wrap gap-space-sm">
        <Button variant="primary" icon="add" disabled={disabled || busy} onClick={onAdd}>
          {busy ? 'Adding…' : addLabel}
        </Button>
        {children}
      </div>
    </div>
  )
}
