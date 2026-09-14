import { Card } from '../../ui'
import type { StatsTotals } from '../../lib/api'
import { Figure } from './Figure'
import { grouped } from './labels'

/**
 * What the library holds, whichever period is selected.
 *
 * None of these six is windowed — they count the index as it stands today —
 * so the section says that out loud rather than letting the period control
 * above imply otherwise.
 */
export function TotalsGrid({ totals }: { totals: StatsTotals }) {
  return (
    <Card as="section" elevated>
      <h2 className="text-title-md text-on-surface">Library totals</h2>
      <p className="mt-space-xs text-body-sm text-on-surface-variant">
        Everything the index holds. The period does not move these.
      </p>
      <div className="mt-space-lg grid grid-cols-2 gap-space-lg sm:grid-cols-3 xl:grid-cols-6">
        <Figure label="Series" value={grouped(totals.series)} detail="in the index" />
        <Figure label="Tracked" value={grouped(totals.tracked)} detail="with a status on a list" />
        <Figure label="In Komga" value={grouped(totals.in_komga)} detail="also a series in Komga" />
        <Figure
          label="Chapters known"
          value={grouped(totals.chapters_known)}
          detail="seen on a source"
        />
        <Figure
          label="Downloaded"
          value={grouped(totals.chapters_downloaded)}
          detail="on disk as CBZ"
        />
        <Figure
          label="Chapters read"
          value={grouped(totals.chapters_read)}
          // Summed from where the lists say the reader stands, not from the
          // event log — which is why it can be large on a day the velocity
          // chart is still empty.
          detail="lifetime, from current list progress"
        />
      </div>
    </Card>
  )
}
