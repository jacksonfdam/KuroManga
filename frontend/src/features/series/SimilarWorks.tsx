import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { Card, Icon } from '../../ui'
import type { SimilarWork } from '../../lib/api'

/**
 * AniList's own recommendations for this manga, strongest first.
 *
 * Each one goes somewhere. A work already in the library opens its own page —
 * the API says which, matching on the AniList id both sides came from rather
 * than on the title. Everything else opens AniList in a new tab, which is where
 * the recommendation came from and the only place that can say more about it.
 * The two are told apart on the card, so a click is never a surprise.
 */
export function SimilarWorks({ items }: { items: SimilarWork[] }) {
  if (items.length === 0) return null

  return (
    <Card as="section" elevated className="flex flex-col gap-space-md">
      <h2 className="text-headline-sm text-on-surface">Similar works</h2>
      <div className="flex flex-col gap-space-sm">
        {items.map((item) => (
          <SimilarRow key={item.media_id} item={item} />
        ))}
      </div>
    </Card>
  )
}

function SimilarRow({ item }: { item: SimilarWork }) {
  const body = (
    <>
      <div className="h-16 w-12 shrink-0 overflow-hidden rounded bg-surface-container-highest">
        {item.cover_url && (
          <img src={item.cover_url} alt="" className="h-full w-full object-cover" loading="lazy" />
        )}
      </div>
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="truncate text-body-md font-semibold text-on-surface group-hover:text-primary">
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
        <span className="flex items-center gap-1.5 font-mono text-label-sm text-outline">
          {item.score != null && <span className="text-tertiary">★ {item.score.toFixed(1)}</span>}
          {item.score != null && item.chapters != null && <span>·</span>}
          {item.chapters != null && <span>{item.chapters} chapters</span>}
          {/* Which of the two destinations this row has, said before it is
              clicked rather than discovered by leaving the application. */}
          {item.series_id != null ? (
            <span className="flex items-center gap-1 text-secondary">
              <Icon name="check" className="h-3 w-3" />
              In your library
            </span>
          ) : (
            <span className="flex items-center gap-1">
              <Icon name="link" className="h-3 w-3" />
              AniList
            </span>
          )}
        </span>
      </div>
    </>
  )

  return item.series_id != null ? (
    <Row to={`/series/${item.series_id}`}>{body}</Row>
  ) : (
    <Row href={`https://anilist.co/manga/${item.media_id}`}>{body}</Row>
  )
}

function Row({ to, href, children }: { to?: string; href?: string; children: ReactNode }) {
  const className =
    'group flex items-center gap-space-sm rounded-lg p-1 transition-colors hover:bg-surface-container-high'
  return to ? (
    <Link to={to} className={className}>
      {children}
    </Link>
  ) : (
    <a href={href} target="_blank" rel="noreferrer" className={className}>
      {children}
    </a>
  )
}
