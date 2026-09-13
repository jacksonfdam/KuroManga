import { Card } from '../../ui'
import type { Suggestion } from '../../lib/api'

function whenOf(at?: string): string {
  if (!at) return ''
  const stamp = new Date(at)
  return Number.isNaN(stamp.getTime()) ? '' : ` (${stamp.toLocaleString()})`
}

/**
 * A status the user picked that never reached one of their lists. The card it
 * was chosen on is gone by the time the write job runs, so this is the only
 * place a rejected status or a stale token can still be reported.
 */
export function WriteFailures({ items }: { items: Suggestion[] }) {
  if (items.length === 0) return null
  return (
    <Card>
      <h2 className="text-title-md text-on-surface">Status not saved to every list</h2>
      <ul className="mt-space-sm flex flex-col gap-space-xs">
        {items.map((item) => (
          <li key={item.id} className="text-body-sm text-error">
            {item.title} —{' '}
            {item.write_results
              .filter((result) => !result.ok && !result.skipped)
              .map(
                (result) =>
                  `${result.target}: ${result.error ?? 'failure with no details'}${whenOf(result.at)}`,
              )
              .join(' · ')}
          </li>
        ))}
      </ul>
    </Card>
  )
}
