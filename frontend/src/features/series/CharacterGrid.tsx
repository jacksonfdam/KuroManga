import type { SeriesCharacter } from '../../lib/api'

const ROLE_LABEL: Record<string, string> = {
  MAIN: 'Main',
  SUPPORTING: 'Supporting',
  BACKGROUND: 'Background',
}

/**
 * Only AniList serves characters — MyAnimeList has none for manga at all — so
 * a series synced from MyAnimeList alone shows the empty sentence rather than
 * an empty grid that reads as a loading failure.
 *
 * series_detail only queues media_enrich; it does not wait on it, so
 * `characters` is `[]` on every first load of a series that IS matched to
 * AniList, for as long as the job takes to run. `providers` and `enriched_at`
 * are what tell that case apart from a series AniList has never heard of —
 * without them this rendered the "not matched" sentence on a series that was
 * matched and simply hadn't been fetched yet.
 */
export function CharacterGrid({
  characters,
  providers,
  enrichedAt,
}: {
  characters: SeriesCharacter[]
  providers: string[]
  enrichedAt: string | null
}) {
  if (characters.length === 0) {
    if (providers.includes('anilist') && enrichedAt === null) {
      return <p className="text-body-sm text-outline">Characters are still being fetched.</p>
    }
    return (
      <p className="text-body-sm text-outline">
        No characters recorded. Only AniList publishes them, and this series is not
        matched to an AniList entry.
      </p>
    )
  }

  return (
    <div className="grid grid-cols-2 gap-space-md sm:grid-cols-3 lg:grid-cols-4">
      {characters.map((character) => (
        <div key={character.name} className="flex flex-col gap-space-xs">
          <div className="aspect-[2/3] overflow-hidden rounded-lg bg-surface-container-highest">
            {character.image_url && (
              <img
                src={character.image_url}
                alt=""
                className="h-full w-full object-cover"
                loading="lazy"
              />
            )}
          </div>
          <span className="truncate text-body-sm font-semibold text-on-surface">
            {character.name}
          </span>
          {character.role && (
            <span className="font-mono text-label-sm text-outline">
              {ROLE_LABEL[character.role] ?? character.role}
            </span>
          )}
        </div>
      ))}
    </div>
  )
}
