import type { DiscoverKind } from '../../lib/api'

/**
 * What a reader is choosing between.
 *
 * The card used to name the step owed — "Pick a status", "Pick a source" — and
 * that read as noise beside a panel offering the same control, because the
 * kind is the real distinction: a recommendation, a series missing a source,
 * an anime with no manga found. The filter chips use these same words, so the
 * badge on a card says which chip would keep it.
 */
export const KIND_LABEL: Record<DiscoverKind, string> = {
  suggestion: 'Recommendation',
  review: 'Needs a source',
  unmatched: 'Anime',
}
