import { Badge, Button, EmptyState, ErrorState, NoticeBar, SegmentedControl, Skeleton } from '../../ui'
import { JobRow } from './JobRow'
import { QueueGroupRow } from './QueueGroup'
import { useDownloads, type Grouping } from './useDownloads'

// The same control the library, review and unmatched screens carry.
const GROUPINGS: { value: Grouping; icon: 'grid' | 'list'; label: string }[] = [
  { value: 'series', icon: 'grid', label: 'By series' },
  { value: 'flat', icon: 'list', label: 'Flat' },
]

// No mockup covers this screen. Section headers plus a flat list of JobRow
// reuses the library screen's section/heading rhythm; the four counts read
// as Badge chips whose tones borrow the same primary/secondary/tertiary/error
// vocabulary format.ts's STATUS_TONE already assigns to reading, completed,
// planning and dropped — done, running, pending and failed sit in the same
// emotional register as those four.
export function DownloadsPage() {
  const {
    jobs,
    pendingBySeries,
    running,
    runningByLane,
    grouping,
    setGrouping,
    retryFailed,
    promote,
    cancel,
    counts,
    loaded,
    error,
    reload,
    notice,
    openJob,
    events,
    toggle,
    retry,
  } = useDownloads()

  // "Queue is empty" and "we could not read the queue" look identical from the
  // outside and mean opposite things: one says the pipeline is idle, the other
  // says nothing is known about it.
  if (!loaded && error) {
    return <ErrorState title="Couldn't load the queue" detail={error} onRetry={reload} />
  }

  if (!loaded) {
    return (
      <div className="flex flex-col gap-space-md">
        <Skeleton className="h-10 w-48" />
        {[0, 1, 2].map((slot) => (
          <Skeleton key={slot} className="h-24 w-full" />
        ))}
      </div>
    )
  }

  if (jobs.length === 0) {
    return (
      <div className="flex flex-col gap-space-lg">
        {error && <NoticeBar tone="error" text={`Couldn't refresh the queue: ${error}`} onRetry={reload} />}
        {notice && <NoticeBar tone={notice.tone} text={notice.text} />}
        <EmptyState
          icon="download"
          title="Queue is empty"
          detail="Nothing is downloading right now. Confirm a mapping in Review, or enable auto-download for a series."
        />
      </div>
    )
  }

  const failed = jobs.filter((job) => job.state === 'failed')
  const pending = jobs.filter((job) => job.state === 'pending')
  // A permanent failure is not retryable, so a button offering to retry them
  // all would be offering nothing on a list made only of those.
  const retryable = failed.filter((job) => !job.permanent)

  return (
    <div className="flex flex-col gap-space-xl">
      {error && <NoticeBar tone="error" text={`Couldn't refresh the queue: ${error}`} onRetry={reload} />}
      {notice && <NoticeBar tone={notice.tone} text={notice.text} />}
      <div className="flex flex-col gap-space-sm">
        <h1 className="text-headline-lg font-extrabold tracking-tight text-on-surface">Downloads</h1>
        <div className="flex flex-wrap gap-2">
          <Badge tone="secondary">{counts.leased ?? 0} running</Badge>
          <Badge tone="tertiary">{counts.pending ?? 0} pending</Badge>
          <Badge tone="error">{counts.failed ?? 0} failed</Badge>
          <Badge tone="primary">{counts.done ?? 0} done</Badge>
        </div>
        {/* Per lane, because the lanes are the reason a download backlog no
            longer holds up everything else. Absent while nothing runs rather
            than shown as two zeroes. */}
        {Object.keys(runningByLane).length > 0 && (
          <p className="font-mono text-label-md text-outline">
            Running now:{' '}
            {Object.entries(runningByLane)
              .sort()
              .map(([lane, count]) => `${count} ${lane}`)
              .join(' · ')}
          </p>
        )}
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
        <div className="flex flex-wrap items-center justify-between gap-space-sm">
          <h2 className="text-headline-md font-extrabold tracking-tight text-on-surface">Failed</h2>
          {retryable.length > 0 && (
            <Button variant="surface" size="sm" icon="sync" onClick={retryFailed}>
              Retry all {retryable.length}
            </Button>
          )}
        </div>
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
        <div className="flex flex-wrap items-center justify-between gap-space-sm">
          <div className="flex items-baseline gap-space-sm">
            <h2 className="text-headline-md font-extrabold tracking-tight text-on-surface">Pending</h2>
            <span className="font-mono text-label-md text-outline">
              {pending.length} in {pendingBySeries.length}{' '}
              {pendingBySeries.length === 1 ? 'group' : 'groups'}
            </span>
          </div>
          {pending.length > 0 && (
            <SegmentedControl options={GROUPINGS} value={grouping} onChange={setGrouping} />
          )}
        </div>
        {pending.length === 0 ? (
          <p className="rounded-xl bg-surface-container-low px-space-md py-space-md text-body-sm text-on-surface-variant">
            Queue is empty.
          </p>
        ) : (
          <div className="flex flex-col gap-space-sm">
            {grouping === 'series' ? (
              pendingBySeries.map((group) => (
                <QueueGroupRow
                  key={group.seriesId ?? 'none'}
                  group={group}
                  onPromote={
                    group.seriesId === null
                      ? null
                      : () => promote(group.seriesId as number, group.title)
                  }
                  onCancel={
                    group.seriesId === null
                      ? null
                      : () => cancel(group.seriesId as number, group.title)
                  }
                  renderJob={(job) => (
                    <JobRow
                      key={job.id}
                      job={job}
                      expanded={openJob === job.id}
                      events={openJob === job.id ? events : []}
                      onToggle={() => toggle(job.id)}
                    />
                  )}
                />
              ))
            ) : (
              <>
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
              </>
            )}
          </div>
        )}
      </section>
    </div>
  )
}
