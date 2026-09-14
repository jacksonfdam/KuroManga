import { AddToList, Button } from '../../ui'
import type { Suggestion, SuggestionSource } from '../../lib/api'
import type { ListStatus } from '../../lib/format'
import type { Choice } from './useDiscovery'

/**
 * Why this title is being offered at all: which anime it came from, how far
 * that anime got, and how much manga there is. Without it a suggestion is a
 * title the user has to go and research, which is the work the screen exists
 * to remove — so it is rendered as prose next to the cover, not as a tooltip.
 */
function reasonOf(suggestion: Suggestion): string {
  const { origin_title, origin_status, total_episodes } = suggestion.reason
  if (!origin_title) return 'Related to an anime on your list.'
  const episodes = total_episodes
    ? ` (${total_episodes} episode${total_episodes === 1 ? '' : 's'})`
    : ''
  const watched =
    origin_status === 'completed' ? `completed anime${episodes}` : `airing anime${episodes}`
  const chapters = suggestion.total_chapters
  const beyond = chapters ? ` — the manga runs to chapter ${chapters}` : ''
  return `From ${origin_title}, a ${watched}${beyond}.`
}

// The chips answer "where can I read this", so they are one per site, not one
// per candidate: a title with several MangaDex hits must not repeat the chip.
function uniqueSources(item: Suggestion): SuggestionSource[] {
  const bestBySite = new Map<string, SuggestionSource>()
  for (const source of item.sources) {
    const current = bestBySite.get(source.site)
    if (!current || source.score > current.score) bestBySite.set(source.site, source)
  }
  const preferredSite = item.best_source?.site
  return [...bestBySite.values()].sort((a, b) => {
    if (a.site === preferredSite) return -1
    if (b.site === preferredSite) return 1
    return b.score - a.score
  })
}

export function SuggestionCard({
  item,
  choice,
  busy,
  selected,
  onSelect,
  onStatus,
  onDownload,
  onAdd,
  onDismiss,
}: {
  item: Suggestion
  choice: Choice
  busy: boolean
  selected: boolean
  onSelect: () => void
  onStatus: (status: ListStatus) => void
  onDownload: (download: boolean) => void
  onAdd: () => void
  onDismiss: () => void
}) {
  return (
    <article
      className={`flex flex-col overflow-hidden rounded-xl bg-surface-container-low shadow-card ${selected ? 'ring-1 ring-primary' : ''}`}
    >
      {/* Not the whole card: it already carries the status picker, Add and
          Dismiss below, and a card-wide click target would swallow those. */}
      <button
        type="button"
        onClick={onSelect}
        aria-label={`Show details for ${item.title}`}
        className="aspect-[2/3] w-full overflow-hidden bg-surface-container-highest"
      >
        {item.cover_url && (
          <img src={item.cover_url} alt="" loading="lazy" className="h-full w-full object-cover" />
        )}
      </button>
      <div className="flex flex-1 flex-col gap-space-sm p-space-md">
        <h3 className="text-title-md text-on-surface">
          <button type="button" onClick={onSelect} className="text-left hover:underline">
            {item.title}
          </button>
        </h3>
        <p className="text-body-sm text-on-surface-variant">{reasonOf(item)}</p>
        <div className="flex flex-wrap items-center gap-space-xs">
          {item.year && <span className="font-mono text-label-sm text-outline">{item.year}</span>}
          {uniqueSources(item).map((source) => (
            <span
              key={source.site}
              className={`rounded-full px-space-sm py-0.5 font-mono text-label-sm ${
                source.site === item.best_source?.site
                  ? 'bg-secondary/[0.12] text-secondary'
                  : 'bg-surface-container-high text-on-surface-variant'
              }`}
            >
              {source.site}
            </span>
          ))}
        </div>
        <div className="mt-auto pt-space-xs">
          <AddToList
            idPrefix={`suggestion-${item.id}`}
            status={choice.status}
            download={choice.download}
            busy={busy}
            onStatus={onStatus}
            onDownload={onDownload}
            onAdd={onAdd}
          >
            <Button variant="ghost" disabled={busy} onClick={onDismiss}>
              Dismiss
            </Button>
          </AddToList>
        </div>
      </div>
    </article>
  )
}
