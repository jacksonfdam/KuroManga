import { Button } from '../../ui'
import type { SearchCandidate, UnmatchedAnime, UnmatchedSearch } from '../../lib/api'
import type { ListStatus } from '../../lib/format'
import { SearchResults } from './SearchResults'
import { titleOf } from './labels'
import type { Choice } from './useUnmatched'

/**
 * Everything that can be done to one unmatched anime: ask the providers about
 * it, put it aside, and add whichever candidate comes back.
 *
 * These were the two halves of `AnimeRow`, which made the row the only place
 * the screen could be acted from. A poster tile has no room for a list of
 * search results, so the grid would have been a layout with nothing to do —
 * lifting them out is what lets the detail panel drive the screen instead.
 *
 * They stay two pieces rather than one because the row places them in two
 * places: the buttons sit beside the metadata, the findings below all of it.
 * Folding them together would have quietly restyled the list on the way to
 * building the grid.
 */
export interface UnmatchedActionProps {
  anime: UnmatchedAnime
  found: UnmatchedSearch | undefined
  searching: boolean
  busy: string | null
  showHidden: boolean
  settingFor: (key: string) => Choice
  onSearch: () => void
  onHide: () => void
  onStatus: (key: string, status: ListStatus) => void
  onDownload: (key: string, download: boolean) => void
  onAdd: (candidate: SearchCandidate) => void
}

/** Ask about this one title, or put it aside. */
export function UnmatchedButtons({
  found,
  searching,
  busy,
  showHidden,
  onSearch,
  onHide,
}: Pick<
  UnmatchedActionProps,
  'found' | 'searching' | 'busy' | 'showHidden' | 'onSearch' | 'onHide'
>) {
  return (
    <>
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
    </>
  )
}

/** What came back, and the controls that turn one of it into a series. */
export function UnmatchedFindings({
  anime,
  found,
  searching,
  busy,
  settingFor,
  onStatus,
  onDownload,
  onAdd,
}: Pick<
  UnmatchedActionProps,
  | 'anime'
  | 'found'
  | 'searching'
  | 'busy'
  | 'settingFor'
  | 'onStatus'
  | 'onDownload'
  | 'onAdd'
>) {
  return (
    <>
      {searching && (
        <p className="text-body-sm text-tertiary">
          Asking AniList and MyAnimeList for “{anime.title_romaji || titleOf(anime)}” — two
          providers, so give it a moment.
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
    </>
  )
}
