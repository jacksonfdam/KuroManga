import { Card } from '../../ui'
import type { SimilarWork } from '../../lib/api'

/**
 * AniList's own recommendations for this manga, strongest first. Nothing here
 * is a link: the recommended work is not necessarily on the user's lists, so
 * there is no series of ours to navigate to, and a card that looks clickable
 * and is not is worse than one that does not.
 */
export function SimilarWorks({ items }: { items: SimilarWork[] }) {
  if (items.length === 0) return null

  return (
    <Card as="section" elevated className="flex flex-col gap-space-md">
      <h2 className="text-headline-sm text-on-surface">Similar works</h2>
      <div className="flex flex-col gap-space-sm">
        {items.map((item) => (
          <div key={item.media_id} className="flex items-center gap-space-sm">
            <div className="h-16 w-12 shrink-0 overflow-hidden rounded bg-surface-container-highest">
              {item.cover_url && (
                <img
                  src={item.cover_url}
                  alt=""
                  className="h-full w-full object-cover"
                  loading="lazy"
                />
              )}
            </div>
            <div className="flex min-w-0 flex-col gap-0.5">
              <span className="truncate text-body-md font-semibold text-on-surface">
                {/* Both providers left this one unnamed. The id is the only true name we
                    have for it, and a manufactured word in the title's place would read
                    as the work's actual title. */}
                {item.title ?? `#${item.media_id}`}
              </span>
              {item.genres.length > 0 && (
                <span className="truncate font-mono text-label-sm text-outline">
                  {item.genres.slice(0, 3).join(' · ')}
                </span>
              )}
              <span className="font-mono text-label-sm text-outline">
                {item.score != null && (
                  <span className="text-tertiary">★ {item.score.toFixed(2)}</span>
                )}
                {item.score != null && item.chapters != null && ' · '}
                {item.chapters != null && `${item.chapters} chapters`}
              </span>
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}
