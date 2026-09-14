import { Badge, Card } from '../../ui'
import type { TimeSpent } from '../../lib/api'
import { Figure } from './Figure'
import { formatDay, formatMinutes } from './labels'

/**
 * Three framings of the same assumption, each labelled as one.
 *
 * Nothing in this pipeline observes reading time. Every figure below is
 * chapters multiplied by a number in Settings, and the payload says so in a
 * field of its own rather than trusting a caption to survive — so the badge
 * and the formula are rendered from what it sends, not from what this file
 * remembers about it.
 */
export function TimeSpentPanel({ time }: { time: TimeSpent }) {
  return (
    <Card as="section" elevated>
      <div className="flex flex-wrap items-center gap-space-sm">
        <h2 className="text-title-md text-on-surface">Time spent</h2>
        {time.estimated && <Badge tone="warning">Estimate</Badge>}
      </div>
      <p className="mt-space-xs max-w-3xl text-body-md text-on-surface-variant">
        Nothing here watches a clock. All three figures are chapters multiplied by the{' '}
        {time.minutes_per_chapter} minutes a chapter set in Settings, so they move with that
        setting rather than with how long the reading actually took.
      </p>
      <p className="mt-space-xs font-mono text-label-sm text-outline">{time.basis}</p>

      <div className="mt-space-lg grid grid-cols-1 gap-space-lg sm:grid-cols-3">
        <Figure
          label="In this period"
          value={formatMinutes(time.period_minutes)}
          detail="from the chapters recorded inside the window above"
        />
        <Figure
          label="Since the log began"
          value={formatMinutes(time.recorded_minutes)}
          // A null recorded_from is the day-one case, and the difference
          // matters: zero here means nothing was measured, which is not the
          // same claim as nothing having been read.
          detail={
            time.recorded_from
              ? `every chapter recorded since ${formatDay(time.recorded_from)}`
              : 'nothing has been recorded yet, so this is zero because nothing was measured — not because nothing was read'
          }
        />
        <Figure
          label="Whole library"
          value={formatMinutes(time.library_minutes)}
          detail="from where your lists say you stand, so it covers reading done long before any of this was logged"
        />
      </div>
    </Card>
  )
}
