import { Button } from '../../ui'
import type { SearchCandidate, UnmatchedAnime, UnmatchedSearch } from '../../lib/api'
import type { ListStatus } from '../../lib/format'
import { SearchResults } from './SearchResults'
import { episodesCounted, providerName, titleOf } from './labels'
import type { Choice } from './useUnmatched'

export function AnimeRow({
  anime,
  found,
  searching,
  busy,
  showHidden,
  selected,
  settingFor,
  onSearch,
  onHide,
  onSelect,
  onStatus,
  onDownload,
  onAdd,
}: {
  anime: UnmatchedAnime
  found: UnmatchedSearch | undefined
  searching: boolean
  busy: string | null
  showHidden: boolean
  selected: boolean
  settingFor: (key: string) => Choice
  onSearch: () => void
  onHide: () => void
  onSelect: () => void
  onStatus: (key: string, status: ListStatus) => void
  onDownload: (key: string, download: boolean) => void
  onAdd: (candidate: SearchCandidate) => void
}) {
  const name = titleOf(anime)

  return (
    <article
      className={`flex flex-col gap-space-md rounded-xl bg-surface-container p-space-md shadow-sm ${selected ? 'ring-1 ring-primary' : ''}`}
    >
      <div className="flex flex-col gap-space-md sm:flex-row sm:items-start">
        {/* Not the whole row: it already carries Search, Hide and Add below,
            and a row-wide click target would swallow clicks meant for those. */}
        <button
          type="button"
          onClick={onSelect}
          aria-label={`Show details for ${name}`}
          className="aspect-[2/3] w-14 shrink-0 overflow-hidden rounded-lg bg-surface-container-highest"
        >
          {anime.cover_url && (
            <img src={anime.cover_url} alt="" loading="lazy" className="h-full w-full object-cover" />
          )}
        </button>
        <div className="flex min-w-0 flex-1 flex-col gap-space-xs">
          <h3 className="text-title-md text-on-surface">
            <button type="button" onClick={onSelect} className="text-left hover:underline">
              {name}
            </button>
          </h3>
          {anime.title_romaji && anime.title_romaji !== name && (
            <span className="font-mono text-label-sm text-outline">{anime.title_romaji}</span>
          )}
          <div className="flex flex-wrap items-center gap-space-sm font-mono text-label-sm text-outline">
            <span className="rounded-full bg-surface-container-high px-space-sm py-0.5 text-on-surface-variant">
              {anime.status.replace('_', ' ')}
            </span>
            {episodesCounted(anime) ? (
              <span>
                {anime.progress_episode} / {anime.total_episodes ?? '?'} episode
                {anime.total_episodes === 1 ? '' : 's'} watched
              </span>
            ) : (
              anime.total_episodes !== null && (
                <span>
                  {anime.total_episodes} episode{anime.total_episodes === 1 ? '' : 's'}
                </span>
              )
            )}
            {anime.providers.map((provider) => (
              <span
                key={provider}
                className="rounded-full bg-surface-container-high px-space-sm py-0.5 text-on-surface-variant"
              >
                {providerName(provider)}
              </span>
            ))}
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap gap-space-sm">
          {!showHidden && (
            <Button
              variant="primary"
              icon="search"
              disabled={searching || busy !== null}
              onClick={onSearch}
              title="Asks AniList and MyAnimeList about this one title"
            >
              {searching ? 'Searching…' : found ? 'Search again' : 'Search by title'}
            </Button>
          )}
          <Button variant="ghost" disabled={busy !== null} onClick={onHide}>
            {showHidden ? 'Unhide' : 'Hide'}
          </Button>
        </div>
      </div>

      {searching && (
        <p className="text-body-sm text-tertiary">
          Asking AniList and MyAnimeList for “{anime.title_romaji || name}” — two providers, so give
          it a moment.
        </p>
      )}

      {found && (
        <SearchResults
          anime={anime}
          found={found}
          busy={busy}
          settingFor={settingFor}
          onStatus={onStatus}
          onDownload={onDownload}
          onAdd={onAdd}
        />
      )}
    </article>
  )
}
