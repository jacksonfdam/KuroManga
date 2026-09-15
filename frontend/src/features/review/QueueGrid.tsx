import { Badge, Button } from '../../ui'
import type { QueueProps } from './QueueList'

/**
 * The queue as covers, for the question a list answers badly: which of these
 * do I recognise. A row states a title, and a romanised title is often not how
 * the reader knows the work — the art is.
 *
 * The same component draws the ignored grid, on `QueueList`'s reasoning: the
 * two answer opposite questions but a tile is a tile, and two near-identical
 * grids are how two views that should teach each other start disagreeing about
 * what a series looks like. What differs is passed in.
 */
export function QueueGrid({ items, position, skipped, busy, onPick, onUnignore }: QueueProps) {
  return (
    <div className="grid grid-cols-2 gap-space-md sm:grid-cols-3 xl:grid-cols-5">
      {items.map((item, index) => {
        const here = position === index
        return (
          <article
            key={item.id}
            className={`flex flex-col overflow-hidden rounded-xl bg-surface-container-low shadow-card ${
              here ? 'ring-1 ring-primary' : ''
            }`}
          >
            {/* Only the art is the target: the tile carries its own button
                below, and a tile-wide click would swallow it. */}
            <button
              type="button"
              disabled={!onPick}
              onClick={() => onPick?.(index)}
              aria-label={onPick ? `Review ${item.title}` : item.title}
              className="relative aspect-[2/3] w-full overflow-hidden bg-surface-container-highest"
            >
              {item.cover_url && (
                <img
                  src={item.cover_url}
                  alt=""
                  loading="lazy"
                  className="h-full w-full object-cover"
                />
              )}
              {position !== null && (
                // The queue is walked in order, so a tile has to say where in
                // that order it sits — the list gets this from its own rows.
                <span className="absolute left-1.5 top-1.5 rounded-md bg-surface-container-lowest/90 px-1.5 py-0.5 font-mono text-label-sm text-on-surface">
                  {index + 1}
                </span>
              )}
            </button>

            <div className="flex flex-1 flex-col gap-space-xs p-space-md">
              <h3 className="text-title-md text-on-surface">
                {onPick ? (
                  <button
                    type="button"
                    onClick={() => onPick(index)}
                    className="line-clamp-2 text-left hover:underline"
                  >
                    {item.title}
                  </button>
                ) : (
                  <span className="line-clamp-2">{item.title}</span>
                )}
              </h3>

              {/* The one fact that says whether a tile is a click from done or
                  a dead end, which is the whole reason to scan the queue. */}
              <span className="font-mono text-label-sm text-outline">
                {item.candidate_count === 0
                  ? 'No candidates yet'
                  : `${item.candidate_count} candidate${item.candidate_count === 1 ? '' : 's'}`}
              </span>

              {skipped.has(item.id) && (
                <span className="w-fit">
                  <Badge tone="warning">Skipped</Badge>
                </span>
              )}

              <div className="mt-auto pt-space-xs">
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
              </div>
            </div>
          </article>
        )
      })}
    </div>
  )
}
