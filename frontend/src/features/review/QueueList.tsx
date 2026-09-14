import { Badge, Button } from '../../ui'
import type { ReviewQueueItem } from '../../lib/api'

/**
 * The queue as a list, so the user can see what is ahead instead of only what
 * is in front of them — and jump to any of it without leaving Review.
 *
 * The same component draws the ignored list: the two answer opposite questions
 * ("what is coming" and "what did I turn down") but a row is a row, and two
 * near-identical lists are how two screens that should teach each other start
 * disagreeing about what a series looks like. What differs is passed in.
 */
export function QueueList({
  items,
  position,
  skipped,
  busy,
  onPick,
  onUnignore,
}: {
  items: ReviewQueueItem[]
  /** Where the one-at-a-time view is standing, so the list can mark it. Null on
      the ignored tab, which has no position at all. */
  position: number | null
  skipped: Set<number>
  busy: boolean
  onPick: ((index: number) => void) | null
  onUnignore: ((item: ReviewQueueItem) => void) | null
}) {
  return (
    <ul className="flex flex-col gap-space-sm">
      {items.map((item, index) => {
        const here = position === index
        return (
          <li
            key={item.id}
            className={`flex items-center gap-space-md rounded-xl bg-surface-container-low p-space-sm shadow-sm ${
              here ? 'ring-1 ring-primary' : ''
            }`}
          >
            {position !== null && (
              <span className="w-10 shrink-0 text-right font-mono text-label-sm text-outline">
                {index + 1}
              </span>
            )}
            <div className="aspect-[2/3] w-10 shrink-0 overflow-hidden rounded bg-surface-container-highest">
              {item.cover_url && (
                <img
                  src={item.cover_url}
                  alt=""
                  loading="lazy"
                  className="h-full w-full object-cover"
                />
              )}
            </div>

            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <div className="flex min-w-0 flex-wrap items-center gap-space-xs">
                {onPick ? (
                  <button
                    type="button"
                    onClick={() => onPick(index)}
                    className="truncate text-left text-body-md text-on-surface hover:underline"
                  >
                    {item.title}
                  </button>
                ) : (
                  <span className="truncate text-body-md text-on-surface">{item.title}</span>
                )}
                {skipped.has(item.id) && <Badge tone="warning">Skipped</Badge>}
              </div>
              {/* The one fact that says whether a row is a click from done or a
                  dead end, which is the whole reason to scan this list. */}
              <span className="font-mono text-label-sm text-outline">
                {item.candidate_count === 0
                  ? 'No candidates yet'
                  : `${item.candidate_count} candidate${item.candidate_count === 1 ? '' : 's'}`}
              </span>
            </div>

            {onPick && (
              <Button variant="surface" size="sm" onClick={() => onPick(index)}>
                {here ? 'Back to it' : 'Review this one'}
              </Button>
            )}
            {onUnignore && (
              <Button
                variant="surface"
                size="sm"
                icon="sync"
                disabled={busy}
                onClick={() => onUnignore(item)}
              >
                Put back in the queue
              </Button>
            )}
          </li>
        )
      })}
    </ul>
  )
}
