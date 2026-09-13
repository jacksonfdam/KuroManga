import { Button, Icon, ProgressBar } from '../../ui'
import type { Job, JobEvent } from '../../lib/api'
import { jobLabel } from './useDownloads'
import { JobEventLog } from './JobEventLog'

// Job state is a queue concept, not a list status, so it gets its own small
// tone map rather than forcing StatusPill's ListStatus typing to fit a
// different domain. Built "StatusPill-shaped" — same pill, dot and 12% tint —
// so the two read as the same kind of thing without being the same component.
const TONE: Record<string, 'secondary' | 'tertiary' | 'error' | 'primary'> = {
  leased: 'secondary',
  pending: 'tertiary',
  failed: 'error',
  done: 'primary',
}

const LABEL: Record<string, string> = {
  leased: 'Running',
  pending: 'Pending',
  failed: 'Failed',
  done: 'Done',
}

// The bracket form is load-bearing: 12 isn't on Tailwind's opacity scale
// (0, 5, 10, 15, ...), so a plain `/12` modifier compiles to no rule and the
// badge renders with no fill at all.
const TINT: Record<string, string> = {
  secondary: 'bg-secondary/[0.12] text-secondary',
  tertiary: 'bg-tertiary/[0.12] text-tertiary',
  error: 'bg-error/[0.12] text-error',
  primary: 'bg-primary/[0.12] text-primary',
}

function JobStateBadge({ state }: { state: string }) {
  const tone = TONE[state] ?? 'tertiary'
  return (
    <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-space-sm py-0.5 font-mono text-label-sm ${TINT[tone]}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {LABEL[state] ?? state}
    </span>
  )
}

// No mockup covers this screen. One row shape serves all three sections
// (running, failed, pending) rather than a bespoke table per section, since
// the same three facts — state, progress, log — apply to every job.
export function JobRow({
  job,
  expanded,
  events,
  onToggle,
  onRetry,
}: {
  job: Job
  expanded: boolean
  events: JobEvent[]
  onToggle: () => void
  onRetry?: () => void
}) {
  // The chevron alone is a visual-only cue (and aria-hidden); aria-expanded
  // plus aria-controls is what tells assistive tech this button is a
  // disclosure and which region it opens.
  const logId = `job-${job.id}-log`

  return (
    <div className="rounded-xl bg-surface-container-low p-4 shadow-card">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        aria-controls={logId}
        className="flex w-full items-start justify-between gap-3 text-left"
      >
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <JobStateBadge state={job.state} />
            <span className="truncate text-body-md font-bold text-on-surface">{jobLabel(job)}</span>
          </div>
          {job.last_message && (
            <p className="mt-1 truncate font-mono text-label-sm text-outline">{job.last_message}</p>
          )}
          <div className="mt-2">
            <ProgressBar value={job.pct ?? 0} max={100} tone="secondary" />
          </div>
        </div>
        <Icon
          name="chevron"
          className={`h-5 w-5 shrink-0 text-outline transition-transform ${expanded ? 'rotate-180' : ''}`}
        />
      </button>

      {job.state === 'failed' && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-surface-container-highest/40 pt-3">
          <div className="min-w-0">
            <p className="font-mono text-label-sm text-outline">
              {job.attempts}/{job.max_attempts} attempts
            </p>
            {job.last_error && <p className="truncate text-body-sm text-error">{job.last_error.slice(0, 300)}</p>}
          </div>
          {onRetry && (
            <Button variant="surface" size="sm" icon="sync" onClick={onRetry}>
              Retry
            </Button>
          )}
        </div>
      )}

      {/* Kept mounted (rather than unmounted when collapsed) so aria-controls
          always resolves to a real element instead of a dangling id. */}
      <div id={logId} hidden={!expanded} className="mt-3 border-t border-surface-container-highest/40 pt-3">
        <JobEventLog events={events} />
      </div>
    </div>
  )
}
