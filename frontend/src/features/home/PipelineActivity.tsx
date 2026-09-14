import { Link } from 'react-router-dom'

import { Icon, ProgressBar } from '../../ui'
import type { Job, WorkerState } from '../../lib/api'
import { relativeTime } from '../../lib/format'

// The Downloads screen builds the same label from the same two fields. A
// feature folder may not import another and this is four lines, so it is
// copied rather than routed through `lib/` — the rule the repo already keeps
// for helpers this small.
function jobLabel(job: Job): string | null {
  if (job.chapter_number !== null) {
    return `${job.series_title ?? 'unknown'} · Ch.${job.chapter_number}`
  }
  return job.series_title
}

const OUTCOME: Record<string, { label: string; tint: string }> = {
  done: { label: 'Done', tint: 'text-secondary' },
  failed: { label: 'Failed', tint: 'text-error' },
}

function Running({ job }: { job: Job }) {
  return (
    <div className="flex flex-col gap-space-xs rounded-xl bg-surface-container-low p-space-md shadow-sm">
      <div className="flex items-baseline gap-space-sm">
        <span className="min-w-0 flex-1 truncate text-body-md font-bold text-on-surface">
          {jobLabel(job) ?? job.type}
        </span>
        {/* Nothing has reported a percentage for this job yet. A bar at 0%
            would claim it had started and got nowhere. */}
        {job.pct !== null && (
          <span className="shrink-0 font-mono text-label-md text-secondary">
            {Math.round(job.pct)}%
          </span>
        )}
      </div>
      <p className="truncate font-mono text-label-sm text-outline">
        {job.last_message || job.type}
      </p>
      {job.pct !== null && <ProgressBar value={job.pct} max={100} tone="secondary" />}
    </div>
  )
}

function Finished({ job }: { job: Job }) {
  const outcome = OUTCOME[job.state] ?? { label: job.state, tint: 'text-outline' }
  return (
    <div className="flex items-baseline gap-space-sm px-space-sm">
      <span className={`shrink-0 font-mono text-label-sm ${outcome.tint}`}>{outcome.label}</span>
      <span className="min-w-0 flex-1 truncate text-body-sm text-on-surface-variant">
        {jobLabel(job) ?? job.type}
      </span>
      <span className="shrink-0 font-mono text-label-sm text-outline">
        {job.finished_at ? relativeTime(job.finished_at) : ''}
      </span>
    </div>
  )
}

export function PipelineActivity({
  running,
  recent,
  worker,
}: {
  running: Job[]
  recent: Job[]
  worker: WorkerState
}) {
  return (
    <section className="flex flex-col gap-space-md">
      <div className="flex flex-wrap items-center gap-space-sm">
        <Icon name="server" className="h-5 w-5 text-primary" />
        <div className="min-w-0">
          <h2 className="text-headline-md font-extrabold tracking-tight text-on-surface">
            Pipeline activity
          </h2>
          <p className="font-mono text-label-sm text-outline">The async queue.</p>
        </div>
        <Link to="/downloads" className="ml-auto font-mono text-label-md text-primary hover:underline">
          Open the queue
        </Link>
      </div>

      {/* Only the stalled case is worth announcing. There is no worker
          heartbeat in this system, so an idle worker and a stopped one look
          identical from here and neither may be reported as "running". An
          expired lease is the one thing the leases do prove. */}
      {worker.state === 'stalled' && (
        <p className="rounded-xl bg-warning/[0.12] px-space-md py-space-sm font-mono text-label-sm text-warning">
          {worker.expired_leases} lease{worker.expired_leases === 1 ? '' : 's'} expired — a worker
          stopped mid-job. They go back in the queue within a minute.
        </p>
      )}

      <div className="flex flex-col gap-space-sm">
        {running.length === 0 ? (
          <p className="rounded-xl bg-surface-container-low px-space-md py-space-md text-body-sm text-on-surface-variant">
            Nothing running.
          </p>
        ) : (
          running.map((job) => <Running key={job.id} job={job} />)
        )}
      </div>

      <div className="flex flex-col gap-space-sm">
        <h3 className="font-mono text-label-sm uppercase tracking-wider text-outline">
          Last finished
        </h3>
        {recent.length === 0 ? (
          <p className="px-space-sm text-body-sm text-on-surface-variant">
            Nothing has finished yet.
          </p>
        ) : (
          recent.map((job) => <Finished key={job.id} job={job} />)
        )}
      </div>
    </section>
  )
}
