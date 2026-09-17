import { Badge } from '../../ui'
import type { DiscoverItem } from '../../lib/api'
import { KIND_LABEL } from './labels'

/**
 * One item, and which of the three it is.
 *
 * The badge named the step owed until that turned out to say nothing a reader
 * could use: the panel offers the control anyway, and the one step left is
 * implied by the kind. So the badge carries the kind, in the same words as the
 * filter chips - it says which chip would keep this card.
 *
 * What is worth a second badge is being one click from done, because that is
 * the promise the ordering makes.
 */
export function DiscoverCard({
  item,
  selected,
  onOpen,
}: {
  item: DiscoverItem
  selected: boolean
  onOpen: () => void
}) {
  return (
    <article
      className={`flex flex-col overflow-hidden rounded-xl bg-surface-container-low shadow-card ${
        selected ? 'ring-1 ring-primary' : ''
      }`}
    >
      <button
        type="button"
        onClick={onOpen}
        aria-label={`Open ${item.title}`}
        className="aspect-[2/3] w-full overflow-hidden bg-surface-container-highest"
      >
        {item.cover_url && (
          <img src={item.cover_url} alt="" loading="lazy" className="h-full w-full object-cover" />
        )}
      </button>

      <div className="flex flex-1 flex-col gap-space-xs p-space-md">
        <h3 className="text-title-md text-on-surface">
          <button type="button" onClick={onOpen} className="line-clamp-2 text-left hover:underline">
            {item.title}
          </button>
        </h3>
        <p className="line-clamp-2 text-body-sm text-on-surface-variant">{item.why}</p>

        <div className="mt-auto flex flex-wrap items-center gap-space-xs pt-space-xs">
          {/* Said plainly, because it is the whole promise of the ordering: this
              one needs a single click and the feed put it here for that reason. */}
          <span className="rounded-full bg-surface-container-high px-space-sm py-0.5 font-mono text-label-sm text-on-surface-variant">
            {KIND_LABEL[item.kind]}
          </span>
          {item.confident && <Badge tone="secondary">One click</Badge>}
        </div>
      </div>
    </article>
  )
}
