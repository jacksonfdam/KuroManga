import { Link } from 'react-router-dom'

import { Button, Icon } from '../../ui'
import type { DashboardSuggestion } from '../../lib/api'
import { PROVIDER_LABEL } from '../../lib/format'

/**
 * How far the anime got, which is the closest true thing to the mockup's
 * "resume at chapter N".
 *
 * No episode-to-chapter mapping exists anywhere in the schema or in either
 * provider's relation edges, so a chapter number here would be invented. What
 * the payload does carry is where the watching stopped, and saying that
 * plainly is more use than a made-up chapter.
 */
function watchedLine(item: DashboardSuggestion): string | null {
  const { episodes_watched, total_episodes, origin_status } = item.reason
  if (episodes_watched === null && total_episodes === null) return null
  if (origin_status === 'completed' && total_episodes) {
    return `Anime finished at episode ${total_episodes}`
  }
  if (episodes_watched === null) return null
  return total_episodes
    ? `Watched to episode ${episodes_watched} of ${total_episodes}`
    : `Watched to episode ${episodes_watched}`
}

function Highlight({
  item,
  busy,
  onApprove,
  onDismiss,
}: {
  item: DashboardSuggestion
  busy: boolean
  onApprove: () => void
  onDismiss: () => void
}) {
  const origin = item.reason.origin_title
  const provider = item.reason.origin_provider
  const watched = watchedLine(item)

  return (
    <article className="flex gap-space-md rounded-xl bg-surface-container-low p-space-md shadow-sm">
      <div className="h-24 w-16 shrink-0 overflow-hidden rounded-lg bg-surface-container-highest">
        {item.cover_url && (
          <img src={item.cover_url} alt={`Cover of ${item.title}`} loading="lazy" className="h-full w-full object-cover" />
        )}
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-space-xs">
        <div className="flex items-start gap-space-sm">
          <div className="min-w-0 flex-1">
            {origin && (
              <span className="inline-block max-w-full truncate rounded-full bg-primary/[0.12] px-space-sm py-0.5 font-mono text-label-sm text-primary">
                From {origin}
                {provider && ` · ${PROVIDER_LABEL[provider] ?? provider}`}
              </span>
            )}
          </div>
          {/* rank_score is a 0..1 ordering weight, so it is shown as the rank
              it is rather than dressed up as a match percentage. */}
          <span
            className="shrink-0 font-mono text-label-sm text-outline"
            title="How strongly this is ranked among the suggestions waiting"
          >
            rank {Math.round(item.rank_score * 100)}
          </span>
        </div>

        <h3 className="truncate text-body-md font-bold text-on-surface" title={item.title}>
          {item.title}
        </h3>

        {watched && <p className="font-mono text-label-sm text-outline">{watched}</p>}

        <div className="mt-auto flex flex-wrap gap-space-sm pt-space-xs">
          <Button variant="primary" size="sm" icon="add" disabled={busy} onClick={onApprove}>
            {busy ? 'Adding…' : 'Approve'}
          </Button>
          <Button variant="ghost" size="sm" disabled={busy} onClick={onDismiss}>
            Dismiss
          </Button>
        </div>
      </div>
    </article>
  )
}

export function DiscoveryHighlights({
  items,
  busy,
  onApprove,
  onDismiss,
}: {
  items: DashboardSuggestion[]
  busy: number | null
  onApprove: (item: DashboardSuggestion) => void
  onDismiss: (item: DashboardSuggestion) => void
}) {
  return (
    <section className="flex flex-col gap-space-md">
      <div className="flex flex-wrap items-center gap-space-sm">
        <Icon name="sparkle" className="h-5 w-5 text-primary" />
        <div className="min-w-0">
          <h2 className="text-headline-md font-extrabold tracking-tight text-on-surface">
            Discovery highlights
          </h2>
          <p className="font-mono text-label-sm text-outline">
            Based on the anime you have watched.
          </p>
        </div>
        <Link to="/discovery" className="ml-auto font-mono text-label-md text-primary hover:underline">
          See all
        </Link>
      </div>

      {items.length === 0 ? (
        <p className="rounded-xl bg-surface-container-low px-space-md py-space-md text-body-sm text-on-surface-variant">
          Nothing waiting. Every anime on your lists already has a manga match, or you have
          answered for the ones that did not.
        </p>
      ) : (
        <div className="flex flex-col gap-space-sm">
          {items.map((item) => (
            <Highlight
              key={item.id}
              item={item}
              busy={busy === item.id}
              onApprove={() => onApprove(item)}
              onDismiss={() => onDismiss(item)}
            />
          ))}
        </div>
      )}
    </section>
  )
}
