import type { UnmatchedAnime } from '../../lib/api'
import { episodesCounted, titleOf } from './labels'

/**
 * The unmatched list as covers.
 *
 * The row it stands beside carries the search and its results inline, which is
 * what makes the row tall — twenty-five of them is a long scroll for the
 * question "which of these do I recognise". A tile answers that question and
 * nothing else: acting on one happens in the detail panel, which is why the
 * actions had to move there first.
 */
function AnimeTile({
  anime,
  selected,
  onSelect,
}: {
  anime: UnmatchedAnime
  selected: boolean
  onSelect: () => void
}) {
  const name = titleOf(anime)

  return (
    <article
      className={`flex flex-col overflow-hidden rounded-xl bg-surface-container-low shadow-card ${
        selected ? 'ring-1 ring-primary' : ''
      }`}
    >
      <button
        type="button"
        onClick={onSelect}
        aria-label={`Show details for ${name}`}
        className="aspect-[2/3] w-full overflow-hidden bg-surface-container-highest"
      >
        {anime.cover_url && (
          <img src={anime.cover_url} alt="" loading="lazy" className="h-full w-full object-cover" />
        )}
      </button>

      <div className="flex flex-1 flex-col gap-space-xs p-space-md">
        <h3 className="text-title-md text-on-surface">
          <button type="button" onClick={onSelect} className="line-clamp-2 text-left hover:underline">
            {name}
          </button>
        </h3>

        <div className="mt-auto flex flex-wrap items-center gap-space-xs pt-space-xs font-mono text-label-sm text-outline">
          <span className="rounded-full bg-surface-container-high px-space-sm py-0.5 text-on-surface-variant">
            {anime.status.replace('_', ' ')}
          </span>
          {/* The counter shows only once it has been filled in: a completed
              entry very often never had it set, and "completed · 0 / 12" reads
              as a contradiction. Above zero it reads; at zero the total alone
              says what is known. */}
          {episodesCounted(anime) ? (
            <span>
              {anime.progress_episode} / {anime.total_episodes ?? '?'}
            </span>
          ) : (
            anime.total_episodes !== null && (
              <span>
                {anime.total_episodes} episode{anime.total_episodes === 1 ? '' : 's'}
              </span>
            )
          )}
        </div>
      </div>
    </article>
  )
}

export function AnimeGrid({
  items,
  selectedId,
  onSelect,
}: {
  items: UnmatchedAnime[]
  selectedId: number | null
  onSelect: (id: number) => void
}) {
  return (
    <div className="grid grid-cols-2 gap-space-md sm:grid-cols-3 xl:grid-cols-5">
      {items.map((anime) => (
        <AnimeTile
          key={anime.id}
          anime={anime}
          selected={selectedId === anime.id}
          onSelect={() => onSelect(anime.id)}
        />
      ))}
    </div>
  )
}
