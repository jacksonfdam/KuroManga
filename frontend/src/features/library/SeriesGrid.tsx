import type { Series } from '../../lib/api'
import { CoverCard } from './CoverCard'

// grid-cols-2 is the mobile default; sm: swaps to an auto-fill track so wide
// viewports pack as many 160-220px posters as fit instead of stretching two.
export function SeriesGrid({
  series,
  pending,
  onIncrement,
}: {
  series: Series[]
  /** Series whose last +1 is queued and not yet written. */
  pending: ReadonlySet<number>
  onIncrement: (id: number, next: number) => Promise<void>
}) {
  return (
    <div className="grid grid-cols-2 gap-5 sm:grid-cols-[repeat(auto-fill,minmax(160px,220px))]">
      {series.map((row) => (
        <CoverCard key={row.id} series={row} pending={pending.has(row.id)} onIncrement={onIncrement} />
      ))}
    </div>
  )
}
