import { Card, EmptyState } from '../../ui'
import type { SeriesReadingFrequency } from '../../lib/api'
import { formatChapter } from '../../lib/format'

// Two literal class names, picked between at render time rather than built
// from a variable — Tailwind's build-time scanner only ever sees the two
// full strings written here, never a name assembled out of a piece of data.
const BAR_TONE = 'bg-secondary'
const BUSIEST_TONE = 'bg-tertiary'

/** The same locale rendering `ProgressManager`'s date rows use, so "recording
    since" reads the same way as every other date on this screen. */
function onDay(iso: string): string {
  const parsed = new Date(iso)
  return Number.isNaN(parsed.getTime()) ? iso : parsed.toLocaleDateString('en-GB')
}

function Header() {
  return <h2 className="text-headline-sm text-on-surface">Reading frequency</h2>
}

/**
 * The series detail mockup's weekly-frequency chart — deferred out of the
 * screen's original build because `progress_event` had not landed on `main`
 * yet.
 * It reads that table directly and infers nothing from progress or list
 * timestamps: a weekday pattern guessed from `updated_at` would be a pattern
 * in when the list was touched, not in when a chapter was actually read.
 *
 * `progress_event` fills forward only from the day it shipped, so the
 * common case for a long time to come is a series with no event at all —
 * not a series read on none of the seven days. Seven zero bars would say
 * the second thing while meaning the first, including for a series with
 * hundreds of chapters already read before tracking existed. That case gets
 * its own explanation instead of a chart it cannot honestly draw.
 *
 * Reimplements the bar idiom `features/stats/Columns.tsx` already draws
 * rather than importing it: feature folders do not share components here,
 * and picking out one busiest weekday from six ordinary ones is a different
 * enough shape from a day-by-day velocity strip that lifting a shared
 * primitive for this single caller would be abstracting ahead of a second
 * need for it.
 */
export function ReadingFrequency({ frequency }: { frequency: SeriesReadingFrequency }) {
  if (!frequency.first_event_at) {
    return (
      <Card as="section" elevated className="flex flex-col gap-space-md">
        <Header />
        <EmptyState
          icon="chart"
          title="Nothing recorded yet"
          detail="This chart counts dated reading events for this series, and that only started being recorded recently. It fills forward from here rather than backfilling history, so a series read for years can still show nothing yet — that is the tracking's age, not a quiet week. Move this series forward to start filling it in."
        />
      </Card>
    )
  }

  const max = frequency.weekdays.reduce((high, day) => Math.max(high, day.chapters), 0)
  const average =
    frequency.active_days > 0 ? frequency.total_chapters / frequency.active_days : null

  return (
    <Card as="section" elevated className="flex flex-col gap-space-md">
      <Header />
      {/* Shown for a young log too, not only a thin one: with the whole
          production database holding one row today, "recording since" will
          read as recent for most series for a long time, and that is the
          honest caveat to keep attached to the chart rather than hiding it
          once the log stops looking new. */}
      <p className="text-body-sm text-on-surface-variant">
        Recording since {onDay(frequency.first_event_at)}.
      </p>

      <div
        role="img"
        aria-label={`Chapters read by weekday since ${onDay(frequency.first_event_at)}: ${formatChapter(frequency.total_chapters)} in total.`}
        className="flex h-32 items-end gap-space-xs"
      >
        {frequency.weekdays.map((day) => {
          const isBusiest = frequency.busiest_weekday === day.weekday
          // Bar height is data, not a design token — it has to be a computed
          // percentage of the week's tallest bucket, so it is set inline
          // rather than through a class Tailwind's scanner could ever match.
          const pct = max > 0 ? Math.max(0, (day.chapters / max) * 100) : 0
          return (
            <div
              key={day.weekday}
              aria-hidden="true"
              title={`${day.label} · ${formatChapter(day.chapters)} chapters`}
              className="flex h-full min-w-0 flex-1 flex-col justify-end"
            >
              <div
                className={`w-full rounded-sm ${isBusiest ? BUSIEST_TONE : BAR_TONE} ${day.chapters > 0 ? '' : 'opacity-25'}`}
                style={{ height: `${pct}%`, minHeight: '2px' }}
              />
            </div>
          )
        })}
      </div>
      <div className="flex gap-space-xs" aria-hidden="true">
        {frequency.weekdays.map((day) => (
          <span
            key={day.weekday}
            className="min-w-0 flex-1 truncate text-center font-mono text-label-sm text-outline"
          >
            {day.label.slice(0, 3)}
          </span>
        ))}
      </div>

      {average != null && (
        <p className="border-t border-outline-variant pt-space-md font-mono text-label-md text-on-surface">
          {formatChapter(average)} chapters per active day
        </p>
      )}
    </Card>
  )
}
