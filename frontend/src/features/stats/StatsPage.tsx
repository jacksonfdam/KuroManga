import { ErrorState, NoticeBar, Skeleton } from '../../ui'
import { PublicationEras } from './PublicationEras'
import { StatsHeader } from './StatsHeader'
import { StatusBreakdown } from './StatusBreakdown'
import { TimeSpentPanel } from './TimeSpentPanel'
import { TopGenres } from './TopGenres'
import { TotalsGrid } from './TotalsGrid'
import { VelocityPanel } from './VelocityPanel'
import { useStats } from './useStats'

/**
 * The second screen #16 asked for, built on the `GET /api/stats` that shipped
 * without anything consuming it.
 *
 * Two sections carry a caveat rather than a number dressed up as one. Velocity
 * is drawn only where reading was actually being recorded, because the log
 * began the day its table shipped and a run of zeros before that would read as
 * a month of reading nothing. Time spent is an estimate — chapters times a
 * setting — and says so beside every one of its three figures.
 *
 * Nothing the payload leaves out is drawn: there is no figure here for how
 * long a chapter really took, no reading streak, and no comparison against a
 * previous period, because none of the three has a source.
 */
export function StatsPage() {
  const { stats, loaded, error, reload, period, setPeriod } = useStats()

  return (
    <div className="flex flex-col gap-space-xl">
      <StatsHeader period={stats?.period ?? null} selected={period} onSelect={setPeriod} />

      {/* Nothing has ever arrived and the request failed. A screen of zeros
          and a screen that could not be read look identical and mean opposite
          things: one says the shelf is empty, the other says nothing is known
          about it. */}
      {!loaded && error ? (
        <ErrorState title="Couldn't load the statistics" detail={error} onRetry={reload} />
      ) : !stats ? (
        <div className="flex flex-col gap-space-xl">
          <Skeleton className="h-36 w-full" />
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-40 w-full" />
          <div className="grid grid-cols-1 gap-space-xl lg:grid-cols-2">
            <Skeleton className="h-72 w-full" />
            <Skeleton className="h-72 w-full" />
          </div>
        </div>
      ) : (
        <>
          {error && (
            <NoticeBar
              tone="error"
              text={`Couldn't refresh the statistics: ${error}`}
              onRetry={reload}
            />
          )}

          <TotalsGrid totals={stats.totals} />
          <VelocityPanel velocity={stats.velocity} period={stats.period} />
          <TimeSpentPanel time={stats.time_spent} />

          <div className="grid grid-cols-1 gap-space-xl lg:grid-cols-2">
            <StatusBreakdown rows={stats.status_distribution} />
            <TopGenres rows={stats.top_genres} />
          </div>

          <PublicationEras
            eras={stats.publication_eras}
            withoutYear={stats.without_publication_year}
          />
        </>
      )}
    </div>
  )
}
