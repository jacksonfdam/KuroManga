import { Card } from '../../ui'
import type { Stats } from '../../lib/api'
import { BarList } from './BarList'

/**
 * The ten commonest genres. The endpoint serves ten at most, so the heading
 * says ten rather than claiming this is the whole vocabulary of the shelf.
 */
export function TopGenres({ rows }: { rows: Stats['top_genres'] }) {
  return (
    <Card as="section" elevated>
      <h2 className="text-title-md text-on-surface">Top genres</h2>
      <p className="mt-space-xs text-body-sm text-on-surface-variant">
        The ten most common across the series on your lists. A series counts once for each genre
        it carries, so these add up to more than the shelf does.
      </p>
      <div className="mt-space-lg">
        {rows.length === 0 ? (
          <p className="text-body-md text-on-surface-variant">
            No genres yet. Neither MyAnimeList nor AniList has returned one for anything tracked
            here, so there is nothing to count.
          </p>
        ) : (
          <BarList
            rows={rows.map((row) => ({ key: row.genre, label: row.genre, value: row.count }))}
          />
        )}
      </div>
    </Card>
  )
}
