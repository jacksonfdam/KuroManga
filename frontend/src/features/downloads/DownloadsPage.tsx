import { Badge, EmptyState } from '../../ui'
import { JobRow } from './JobRow'
import { useDownloads } from './useDownloads'

// No mockup covers this screen. Section headers plus a flat list of JobRow
// reuses the library screen's section/heading rhythm; the four counts read
// as Badge chips whose tones borrow the same primary/secondary/tertiary/error
// vocabulary format.ts's STATUS_TONE already assigns to reading, completed,
// planning and dropped — done, running, pending and failed sit in the same
// emotional register as those four.
export function DownloadsPage() {
  const { jobs, counts, openJob, events, toggle, retry } = useDownloads()

  if (jobs.length === 0) {
    return (
      <EmptyState
        icon="download"
        title="Queue is empty"
        detail="Nothing is downloading right now. Confirm a mapping in Review, or enable auto-download for a series."
      />
    )
  }

  const running = jobs.filter((job) => job.state === 'leased')
  const failed = jobs.filter((job) => job.state === 'failed')
  const pending = jobs.filter((job) => job.state === 'pending')

  return (
    <div className="flex flex-col gap-space-xl">
      <div className="flex flex-col gap-space-sm">
        <h1 className="text-headline-lg font-extrabold tracking-tight text-on-surface">Downloads</h1>
        <div className="flex flex-wrap gap-2">
          <Badge tone="secondary">{counts.leased ?? 0} running</Badge>
          <Badge tone="tertiary">{counts.pending ?? 0} pending</Badge>
          <Badge tone="error">{counts.failed ?? 0} failed</Badge>
          <Badge tone="primary">{counts.done ?? 0} done</Badge>
        </div>
      </div>

      <section className="flex flex-col gap-space-md">
        <h2 className="text-headline-md font-extrabold tracking-tight text-on-surface">Running</h2>
        {running.length === 0 ? (
          <p className="rounded-xl bg-surface-container-low px-space-md py-space-md text-body-sm text-on-surface-variant">
            Nothing running.
          </p>
        ) : (
          <div className="flex flex-col gap-space-sm">
            {running.map((job) => (
              <JobRow
                key={job.id}
                job={job}
                expanded={openJob === job.id}
                events={openJob === job.id ? events : []}
                onToggle={() => toggle(job.id)}
              />
            ))}
          </div>
        )}
      </section>

      <section className="flex flex-col gap-space-md">
        <h2 className="text-headline-md font-extrabold tracking-tight text-on-surface">Failed</h2>
        {failed.length === 0 ? (
          <p className="rounded-xl bg-surface-container-low px-space-md py-space-md text-body-sm text-on-surface-variant">
            No failures.
          </p>
        ) : (
          <div className="flex flex-col gap-space-sm">
            {failed.map((job) => (
              <JobRow
                key={job.id}
                job={job}
                expanded={openJob === job.id}
                events={openJob === job.id ? events : []}
                onToggle={() => toggle(job.id)}
                onRetry={() => retry(job.id)}
              />
            ))}
          </div>
        )}
      </section>

      <section className="flex flex-col gap-space-md">
        <div className="flex items-baseline gap-space-sm">
          <h2 className="text-headline-md font-extrabold tracking-tight text-on-surface">Pending</h2>
          <span className="font-mono text-label-md text-outline">{pending.length}</span>
        </div>
        {pending.length === 0 ? (
          <p className="rounded-xl bg-surface-container-low px-space-md py-space-md text-body-sm text-on-surface-variant">
            Queue is empty.
          </p>
        ) : (
          <div className="flex flex-col gap-space-sm">
            {pending.slice(0, 25).map((job) => (
              <JobRow
                key={job.id}
                job={job}
                expanded={openJob === job.id}
                events={openJob === job.id ? events : []}
                onToggle={() => toggle(job.id)}
              />
            ))}
            {pending.length > 25 && (
              <p className="font-mono text-label-sm text-outline">Showing the first 25.</p>
            )}
          </div>
        )}
      </section>
    </div>
  )
}
