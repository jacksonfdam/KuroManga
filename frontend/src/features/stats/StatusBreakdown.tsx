import { Card } from '../../ui'
import type { Stats } from '../../lib/api'
import { STATUS_LABEL, STATUS_TONE } from '../../lib/format'
import { BarList } from './BarList'

/**
 * The five reading statuses. All five are always served, zero-filled, so a
 * status nobody uses is a row at zero rather than a row that vanished.
 */
export function StatusBreakdown({ rows }: { rows: Stats['status_distribution'] }) {
  // The share is measured against the rows themselves rather than against
  // totals.tracked, so the percentages on this card can only ever add up to
  // the card.
  const total = rows.reduce((sum, row) => sum + row.count, 0)

  return (
    <Card as="section" elevated>
      <h2 className="text-title-md text-on-surface">Reading status</h2>
      <p className="mt-space-xs text-body-sm text-on-surface-variant">
        Every series counted once, under its most recently updated list entry — the same rule a
        Library card uses to pick the status it shows.
      </p>
      <div className="mt-space-lg">
        {total === 0 ? (
          <p className="text-body-md text-on-surface-variant">
            Nothing is tracked yet, so there is no split to show. Connect a list in Settings and
            run a sync.
          </p>
        ) : (
          <BarList
            rows={rows.map((row) => ({
              key: row.status,
              label: STATUS_LABEL[row.status],
              value: row.count,
              detail: `${Math.round((row.count / total) * 100)}%`,
              tone: STATUS_TONE[row.status],
            }))}
          />
        )}
      </div>
    </Card>
  )
}
