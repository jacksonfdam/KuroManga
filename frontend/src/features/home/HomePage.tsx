import { useOutletContext } from 'react-router-dom'

import { ErrorState, NoticeBar, Skeleton } from '../../ui'
import { ContinueReading } from './ContinueReading'
import { CounterCards } from './CounterCards'
import { DiscoveryHighlights } from './DiscoveryHighlights'
import { PipelineActivity } from './PipelineActivity'
import { PipelineHeader } from './PipelineHeader'
import { StoragePanel } from './StoragePanel'
import { useHome } from './useHome'

/**
 * The screen `/` used to stand in for.
 *
 * Home and Library were designed as two sections and only one was built, so
 * the router sent `/` to the library and the library did a front page's job
 * badly. This is the other section: the pipeline at a glance, assembled from
 * the single `GET /api/dashboard` the backend serves for it.
 *
 * Five figures in the design are absent here on purpose, each because nothing
 * measures them and the payload leaves the field out rather than zeroing it:
 * network throughput in MB/s, per-job CPU, a ZFS pool health verdict, the
 * storage split by content type, and a suggestion's "resume at chapter N".
 * The source label over a continue-reading cover goes the same way — the rows
 * carry no mapping. Each omission is noted where it would have been rendered.
 */
export function HomePage() {
  const refreshShell = useOutletContext<() => void>()
  const {
    dashboard,
    loaded,
    error,
    reload,
    notice,
    busy,
    increment,
    forceScan,
    approve,
    dismiss,
  } = useHome(refreshShell)

  // Nothing has ever arrived and the request failed. A dashboard of zeros and
  // a dashboard that could not be read look identical and mean opposite
  // things: one says the pipeline is quiet, the other says nothing is known
  // about it.
  if (!loaded && error) {
    return <ErrorState title="Couldn't load Home" detail={error} onRetry={reload} />
  }

  if (!dashboard) {
    return (
      <div className="flex flex-col gap-space-lg">
        <Skeleton className="h-20 w-full" />
        <div className="grid grid-cols-1 gap-space-md sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((slot) => (
            <Skeleton key={slot} className="h-32 w-full" />
          ))}
        </div>
        <Skeleton className="h-44 w-full" />
        <div className="grid grid-cols-1 gap-space-lg lg:grid-cols-2">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-space-xl">
      {error && <NoticeBar tone="error" text={`Couldn't refresh Home: ${error}`} onRetry={reload} />}
      {notice && <NoticeBar tone={notice.tone} text={notice.text} />}

      <PipelineHeader
        integrations={dashboard.integrations}
        pendingMappings={dashboard.mappings.pending}
        newSuggestions={dashboard.discovery.new}
        onForceScan={forceScan}
      />

      <CounterCards
        activeReading={dashboard.active_reading}
        downloads={dashboard.downloads}
        mappings={dashboard.mappings}
        discovery={dashboard.discovery}
      />

      <ContinueReading
        rows={dashboard.continue_reading}
        active={dashboard.active_reading.series}
        onIncrement={increment}
      />

      <div className="grid grid-cols-1 gap-space-xl lg:grid-cols-2">
        <DiscoveryHighlights
          items={dashboard.suggestions}
          busy={busy}
          onApprove={approve}
          onDismiss={dismiss}
        />
        {/* Storage sits under the activity column, as the design has it: the
            queue and the disk it writes to are one question. */}
        <div className="flex flex-col gap-space-lg">
          <PipelineActivity
            running={dashboard.activity.running}
            recent={dashboard.activity.recent}
            worker={dashboard.worker}
          />
          <StoragePanel storage={dashboard.storage} />
        </div>
      </div>
    </div>
  )
}
