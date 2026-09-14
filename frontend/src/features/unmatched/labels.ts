import type {
  DiscardedRelation,
  SearchProviderError,
  UnmatchedAnime,
  UnmatchedSearch,
} from '../../lib/api'

const PROVIDER_NAMES: Record<string, string> = { anilist: 'AniList', mal: 'MyAnimeList' }

export const providerName = (provider: string) => PROVIDER_NAMES[provider] ?? provider

export const titleOf = (anime: UnmatchedAnime) =>
  anime.title || anime.title_english || anime.title_romaji || `Anime ${anime.media_id}`

/**
 * Whether the episode counter is worth showing at all.
 *
 * MyAnimeList stores the status and the counter separately, and a completed
 * entry very often never had the counter filled in — so a row that prints both
 * reads "completed · 0 / 12 episodes watched" and contradicts itself in front
 * of the user. Above zero the counter is a fact worth having; at zero the
 * total alone says everything that is known.
 */
export const episodesCounted = (anime: Pick<UnmatchedAnime, 'progress_episode'>) =>
  anime.progress_episode > 0

export const candidateKey = (animeId: number, provider: string, mediaId: string) =>
  `${animeId}:${provider}:${mediaId}`

const fold = (title: string) => title.trim().toLowerCase()

/**
 * Which providers actually searched for something other than the title the
 * screen shows — MyAnimeList substitutes a name the anime is also known by, or
 * a trimmed prefix, when the AniList spelling is a query it will refuse.
 * Silent when nothing was substituted: a line that always fires is noise.
 */
export function substitutedQueries(found: UnmatchedSearch): [string, string][] {
  return Object.entries(found.queries).filter(([, query]) => fold(query) !== fold(found.query))
}

/**
 * The four codes ask the user for four different things — authorise, wait,
 * retry, nothing — which is the whole reason the API sends a code instead of a
 * sentence. The last one is the one that must not read as a retry: the provider
 * refuses the query itself and would refuse it again.
 */
export function errorMessage(failure: SearchProviderError): string {
  const who = providerName(failure.provider)
  switch (failure.code) {
    case 'not_connected':
      return `${who} is not connected. Authorise it in Settings, then search again.`
    case 'rate_limited':
      return `${who} is taking too many requests right now. Wait a moment and search again.`
    case 'query_unsupported':
      return `${who} cannot search for any title this anime goes by, so it was not asked. Searching again would answer the same.`
    default:
      return `${who} did not answer. Try the search again.`
  }
}

export const FORMAT_LABELS: Record<string, string> = {
  MANGA: 'Manga',
  MANHWA: 'Manhwa',
  MANHUA: 'Manhua',
  OEL: 'OEL',
}

// AniList's relationType vocabulary is wider than the two the provider ever
// records here (parse_relations drops everything else as noise), but the
// wire sends a plain string and an unrecognised one should still read as
// something rather than fail silently.
const RELATION_PHRASES: Record<string, string> = {
  SOURCE: "this anime's source",
  ADAPTATION: 'an adaptation of this anime',
}

export const relationPhrase = (relation: string) =>
  RELATION_PHRASES[relation] ?? `a ${relation.toLowerCase()} relation`

// A discarded relation can point at a light novel, but AniList's relations
// also cover another anime declared as this one's source or adaptation
// (a remake, a sequel that got re-listed) — the format vocabulary here is
// AniList's full MediaFormat, not just the four in MANGA_FORMATS above.
const DISCARDED_FORMAT_PHRASES: Record<string, string> = {
  NOVEL: 'a light novel',
  ONE_SHOT: 'a one-shot',
  MANGA: 'a manga',
  MANHWA: 'a manhwa',
  MANHUA: 'a manhua',
  OEL: 'an OEL work',
  TV: 'a TV anime',
  TV_SHORT: 'a TV short',
  MOVIE: 'a movie',
  SPECIAL: 'a special',
  OVA: 'an OVA',
  ONA: 'an ONA',
  MUSIC: 'a music video',
}

/**
 * Null is real here — AniList did not say — so it gets its own sentence
 * rather than a placeholder pretending to be a format.
 */
export const discardedFormatPhrase = (format: string | null) =>
  format ? (DISCARDED_FORMAT_PHRASES[format] ?? format.toLowerCase()) : 'an unspecified format'

/** The media id is real; an invented title is not — same rule `titleOf` follows above. */
export const discardedRelationTitle = (relation: DiscardedRelation) =>
  relation.title || `#${relation.media_id}`

export interface KnownStateCopy {
  label: string
  /** A StatusPill-style 12% tint, or the neutral surface for the two that are
      merely history rather than a claim about the library. */
  tint: string
  note: string
  // True only for the state the add route answers with a 409, so the screen
  // never offers a button that cannot work.
  blocks: boolean
}

export const KNOWN_STATES: Record<string, KnownStateCopy> = {
  added: {
    label: 'Already added',
    tint: 'bg-secondary/[0.12] text-secondary',
    note: 'You added this one already — it is in your library.',
    blocks: true,
  },
  on_list: {
    label: 'On your list',
    tint: 'bg-secondary/[0.12] text-secondary',
    note: 'Already on one of your lists. Adding it writes the status you pick over the one you have.',
    blocks: false,
  },
  dismissed: {
    label: 'Dismissed before',
    tint: 'bg-surface-container-high text-on-surface-variant',
    note: 'You turned this one down earlier.',
    blocks: false,
  },
  suggested: {
    label: 'Already suggested',
    tint: 'bg-surface-container-high text-on-surface-variant',
    note: 'This is waiting for you under Discovery.',
    blocks: false,
  },
}
