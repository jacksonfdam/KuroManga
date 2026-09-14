import { Card, EmptyState, Icon } from '../../ui'
import type { StatsPeriod, Velocity } from '../../lib/api'
import { formatChapter } from '../../lib/format'
import { Columns } from './Columns'
import { Figure } from './Figure'
import { SOURCE_PHRASE, formatDay, formatShortDay, grouped } from './labels'

/** "8 through Komga · 4 entered by hand" — only the paths that reported
 * something, because a source at zero is a path nothing came through, not a
 * fact about the reading. */
function sources(bySource: Record<string, number>): string | null {
  const parts = Object.entries(bySource)
    .filter(([, chapters]) => chapters > 0)
    .map(([source, chapters]) => `${formatChapter(chapters)} ${SOURCE_PHRASE[source] ?? `through ${source}`}`)
  return parts.length > 0 ? parts.join(' · ') : null
}

/**
 * Chapters per day, and the one thing this chart must never do.
 *
 * Reading is only counted from dated events, and those started being recorded
 * the day the table shipped. Before that there is no history — not a low one.
 * Thirty zero-height columns would read as a month of reading nothing, so an
 * empty log draws no chart at all and says why instead. Once events exist the
 * buckets begin where measurement began, never before it, and a zero inside
 * the measured range is left standing because there it is a real zero.
 */
export function VelocityPanel({ velocity, period }: { velocity: Velocity; period: StatsPeriod }) {
  const measured = velocity.days_counted
  const missing = Math.max(period.days - measured, 0)
  const bySource = sources(velocity.by_source)

  return (
    <Card as="section" elevated>
      <div className="flex items-center gap-space-sm">
        <Icon name="chart" className="h-5 w-5 text-outline" />
        <h2 className="text-title-md text-on-surface">Reading velocity</h2>
      </div>

      {!velocity.has_history ? (
        <div className="mt-space-md">
          <EmptyState
            icon="chart"
            title="Nothing has been recorded yet"
            detail="This chart counts dated reading events, and nothing was writing them down before the log existed — so this is an empty log, not a stretch of reading nothing. Move a series forward here, or let a Komga sync report a chapter, and the days start filling in from that day on."
          />
        </div>
      ) : (
        <>
          <p className="mt-space-xs text-body-sm text-on-surface-variant">
            {velocity.covers_full_period
              ? `Chapters recorded on each of the ${measured} days in this period.`
              : `Measured from ${formatDay(velocity.tracking_since ?? '')}, when the log began. The ${missing} earlier ${missing === 1 ? 'day' : 'days'} in this period are missing, not empty.`}
          </p>

          <div className="mt-space-md">
            <Columns
              label={`Chapters read on each day from ${formatDay(velocity.from ?? '')} to ${formatDay(velocity.to ?? '')}: ${formatChapter(velocity.chapters)} in total over ${measured} ${measured === 1 ? 'day' : 'days'}.`}
              bars={velocity.days.map((day) => ({
                key: day.date,
                value: day.chapters,
                title: `${formatDay(day.date)} · ${formatChapter(day.chapters)} chapters`,
              }))}
            />
            <div className="mt-space-xs flex items-baseline justify-between font-mono text-label-sm text-outline">
              <span>{formatShortDay(velocity.from ?? '')}</span>
              <span>{formatShortDay(velocity.to ?? '')}</span>
            </div>
          </div>

          {velocity.chapters > 0 ? (
            <div className="mt-space-lg grid grid-cols-1 gap-space-lg sm:grid-cols-3">
              <Figure
                label="Chapters"
                value={grouped(velocity.chapters)}
                detail={bySource}
              />
              <Figure
                label="Average"
                value={`${grouped(velocity.per_day)} a day`}
                // per_day divides by the days measured, not by the days in the
                // period: two days of data in a 30-day window is a real pace,
                // not a fifteenth of one.
                detail={`over the ${measured} ${measured === 1 ? 'day' : 'days'} measured`}
              />
              {velocity.busiest && (
                <Figure
                  label="Busiest day"
                  value={formatShortDay(velocity.busiest.date)}
                  detail={`${formatChapter(velocity.busiest.chapters)} chapters`}
                />
              )}
            </div>
          ) : (
            <p className="mt-space-lg text-body-md text-on-surface-variant">
              {velocity.covers_full_period
                ? `No chapters in these ${period.days} days. The log was running for all of them, so this one is a real zero.`
                : `No chapters since the log began. The ${measured} ${measured === 1 ? 'day' : 'days'} measured so far ${measured === 1 ? 'has' : 'have'} nothing in ${measured === 1 ? 'it' : 'them'}.`}
            </p>
          )}
        </>
      )}
    </Card>
  )
}
