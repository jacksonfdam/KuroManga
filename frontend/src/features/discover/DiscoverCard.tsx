import { Badge } from '../../ui'
import type { DiscoverItem } from '../../lib/api'

const NEED_LABEL: Record<string, string> = {
  match: 'Find the manga',
  status: 'Pick a status',
  source: 'Pick a source',
}

/**
 * One item, and what it still owes.
 *
 * What is shown is the needs, not the kind. A reader does not care whether a
 * row arrived from a suggestion, a mapping queue or an unmatched anime; they
 * care whether it is one click away or a search away - which is also what the
 * order is built on.
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
          {item.confident && <Badge tone="secondary">One click</Badge>}
          {item.needs.map((need) => (
            <span
              key={need}
              className="rounded-full bg-surface-container-high px-space-sm py-0.5 font-mono text-label-sm text-on-surface-variant"
            >
              {NEED_LABEL[need] ?? need}
            </span>
          ))}
        </div>
      </div>
    </article>
  )
}
