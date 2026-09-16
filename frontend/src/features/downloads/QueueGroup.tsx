import { useState } from 'react'

import { Badge, Button, Icon } from '../../ui'
import type { Job } from '../../lib/api'
import type { QueueGroup as Group } from './useDownloads'

/**
 * One series' waiting work, with the two controls that act on it.
 *
 * The queue is promoted and cancelled per series, never per job: a reader
 * wants this manga next, or does not want it at all, and asking them to say so
 * nine times once for each queued chapter is the thing this replaces.
 *
 * Collapsed by default. The count is what a reader scans for; the individual
 * chapters matter only once they have picked the series out of the list.
 */
export function QueueGroupRow({
  group,
  onPromote,
  onCancel,
  renderJob,
}: {
  group: Group
  /** Null for work with no series — nothing to promote or cancel it by. */
  onPromote: (() => void) | null
  onCancel: (() => void) | null
  renderJob: (job: Job) => React.ReactNode
}) {
  const [open, setOpen] = useState(false)
  const lanes = new Set(group.jobs.map((job) => job.lane))

  return (
    <article className="rounded-xl bg-surface-container-low shadow-card">
      <div className="flex flex-wrap items-center gap-space-sm p-space-md">
        <button
          type="button"
          onClick={() => setOpen((was) => !was)}
          aria-expanded={open}
          className="flex min-w-0 flex-1 items-center gap-space-sm text-left"
        >
          <Icon
            name="chevron"
            className={`h-4 w-4 shrink-0 text-outline transition-transform ${open ? '' : '-rotate-90'}`}
          />
          <span className="truncate text-title-md text-on-surface">{group.title}</span>
          <Badge tone="tertiary">
            {group.jobs.length} {group.jobs.length === 1 ? 'job' : 'jobs'}
          </Badge>
          {/* Which worker will take it. The lanes exist so downloads cannot
              crowd out the rest, and naming them here is where that stops
              being an implementation detail. */}
          {[...lanes].sort().map((lane) => (
            <span
              key={lane}
              className="rounded-full bg-surface-container-high px-space-sm py-0.5 font-mono text-label-sm text-on-surface-variant"
            >
              {lane}
            </span>
          ))}
        </button>

        {(onPromote || onCancel) && (
          <div className="flex shrink-0 flex-wrap gap-space-sm">
            {onPromote && (
              <Button variant="surface" size="sm" onClick={onPromote}>
                Move to top
              </Button>
            )}
            {onCancel && (
              <Button variant="ghost" size="sm" onClick={onCancel}>
                Cancel waiting
              </Button>
            )}
          </div>
        )}
      </div>

      {open && (
        <div className="flex flex-col gap-space-sm border-t border-surface-container-highest/40 p-space-md pt-space-md">
          {group.jobs.map((job) => renderJob(job))}
        </div>
      )}
    </article>
  )
}
