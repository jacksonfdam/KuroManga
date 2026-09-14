import { Chip } from '../../ui'
import type { StatsPeriod, StatsPeriodKey } from '../../lib/api'
import { PERIODS, formatDay } from './labels'

/**
 * The period is a control on the screen and a parameter of the request: the
 * endpoint windows the figures it serves, so switching here re-asks rather
 * than filtering a payload that was never the whole history.
 *
 * The control renders above every state, including the skeleton — a switch
 * that removes the switch is a control the user cannot correct.
 */
export function StatsHeader({
  period,
  selected,
  onSelect,
}: {
  /** Null until the first payload for this period lands. */
  period: StatsPeriod | null
  selected: StatsPeriodKey
  onSelect: (period: StatsPeriodKey) => void
}) {
  return (
    <section className="flex flex-col gap-space-md">
      <div className="flex flex-col gap-space-xs">
        <h1 className="text-headline-lg font-extrabold tracking-tight text-on-surface">
          Statistics
        </h1>
        <p className="max-w-3xl text-body-md text-on-surface-variant">
          What the library holds, and what has been read out of it. The period moves the reading
          figures below it; the library totals count everything whichever period is picked.
        </p>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-space-md rounded-2xl bg-surface-container-low p-2 shadow-card">
        <div className="flex flex-wrap items-center gap-space-xs" role="group" aria-label="Period">
          {PERIODS.map((option) => (
            <Chip
              key={option.key}
              active={option.key === selected}
              onClick={() => onSelect(option.key)}
            >
              {option.label}
            </Chip>
          ))}
        </div>
        {period && (
          <span className="px-space-sm font-mono text-label-md text-outline">
            {formatDay(period.from)} – {formatDay(period.to)}
          </span>
        )}
      </div>
    </section>
  )
}
