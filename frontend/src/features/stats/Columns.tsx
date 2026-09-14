const FILL: Record<'secondary' | 'tertiary', string> = {
  secondary: 'bg-secondary',
  tertiary: 'bg-tertiary',
}

export interface Column {
  key: string
  value: number
  /** The whole fact about this column, for a pointer hovering over it. */
  title: string
  /** Under the column. Left off where there are too many columns to label. */
  caption?: string
  /** Above the column, where the count is worth reading without a pointer. */
  top?: string
}

/**
 * A column chart built out of two divs and a percentage.
 *
 * Nothing in this repository draws charts, and two charts on one screen do not
 * pay for a dependency: every column here is one number against the tallest of
 * its siblings. A value of zero still draws a hairline rather than nothing at
 * all — inside a measured range a zero is a fact, and a column missing
 * entirely would read as a day nobody looked at.
 */
export function Columns({
  bars,
  tone = 'secondary',
  label,
}: {
  bars: Column[]
  tone?: keyof typeof FILL
  /** What the chart says, in one sentence, for a reader who cannot see it.
      The columns themselves are hidden from the reading order: a year of them
      announced one at a time is noise, and every figure they carry is repeated
      in the sentences underneath. */
  label: string
}) {
  const max = bars.reduce((high, bar) => Math.max(high, bar.value), 0)
  // Below a hairline the columns of a long window merge into one block; above
  // a dozen columns a wide gap is what makes them read as a series of days.
  const gap = bars.length > 60 ? 'gap-px' : bars.length > 12 ? 'gap-0.5' : 'gap-space-xs'

  return (
    <div role="img" aria-label={label} className="flex flex-col gap-space-xs">
      <div className={`flex h-32 items-end ${gap}`}>
        {bars.map((bar) => (
          <div
            key={bar.key}
            aria-hidden="true"
            title={bar.title}
            className="flex h-full min-w-0 flex-1 flex-col justify-end gap-space-xs"
          >
            {bar.top && (
              <span className="truncate text-center font-mono text-label-sm text-on-surface-variant">
                {bar.top}
              </span>
            )}
            <div
              className={`w-full rounded-sm ${FILL[tone]} ${bar.value > 0 ? '' : 'opacity-25'}`}
              style={{
                height: max > 0 ? `${(bar.value / max) * 100}%` : '0%',
                minHeight: '2px',
              }}
            />
          </div>
        ))}
      </div>
      {bars.some((bar) => bar.caption) && (
        <div className={`flex ${gap}`} aria-hidden="true">
          {bars.map((bar) => (
            <span
              key={bar.key}
              className="min-w-0 flex-1 truncate text-center font-mono text-label-sm text-outline"
            >
              {bar.caption}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
