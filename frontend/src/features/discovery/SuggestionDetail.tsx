import { Badge, DetailPanel } from '../../ui'
import type { Suggestion } from '../../lib/api'
import { PROVIDER_LABEL, relativeTime } from '../../lib/format'

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-space-sm">
      <span className="font-mono text-label-sm text-outline">{label}</span>
      <span className="font-mono text-label-md text-on-surface">{value}</span>
    </div>
  )
}

export function SuggestionDetail({
  suggestion,
  onClose,
}: {
  suggestion: Suggestion
  onClose: () => void
}) {
  const { reason, sources, best_source: best, write_results: writes } = suggestion

  return (
    <DetailPanel title={suggestion.title} onClose={onClose}>
      <div className="aspect-[2/3] w-32 overflow-hidden rounded-lg bg-surface-container-highest">
        {suggestion.cover_url && (
          <img src={suggestion.cover_url} alt="" className="h-full w-full object-cover" />
        )}
      </div>

      <div className="flex flex-col gap-space-xs">
        {suggestion.year != null && <Row label="Year" value={`${suggestion.year}`} />}
        {suggestion.total_chapters != null && (
          <Row label="Chapters" value={`${suggestion.total_chapters}`} />
        )}
        {suggestion.publishing_status && (
          <Row label="Publication" value={suggestion.publishing_status} />
        )}
        {/* The rank is how the list is ordered, so the screen owes the user the
            number it ordered by rather than only the position. */}
        <Row label="Rank score" value={suggestion.rank_score.toFixed(3)} />
      </div>

      <section className="flex flex-col gap-space-xs">
        <h3 className="font-mono text-label-sm uppercase tracking-wide text-outline">
          Why this is here
        </h3>
        {reason.origin_title ? (
          <p className="text-body-md text-on-surface-variant">
            Your anime{' '}
            <span className="font-semibold text-on-surface">{reason.origin_title}</span>
            {reason.relation && <> is linked to it as {reason.relation.toLowerCase()}</>}
            {reason.total_episodes != null && <> across {reason.total_episodes} episodes</>}.
          </p>
        ) : (
          <p className="text-body-sm text-outline">
            No origin anime was recorded for this suggestion.
          </p>
        )}
      </section>

      <section className="flex flex-col gap-space-xs">
        <h3 className="font-mono text-label-sm uppercase tracking-wide text-outline">
          Sources found
        </h3>
        {sources.length === 0 ? (
          <p className="text-body-sm text-on-surface-variant">
            No source site matched this title. Adding it will park it for review rather
            than downloading anything.
          </p>
        ) : (
          sources.map((source) => (
            <div
              key={source.url}
              className="flex items-center justify-between gap-space-sm rounded-lg bg-surface-container-low px-space-sm py-space-xs"
            >
              <div className="flex min-w-0 flex-col">
                <span className="text-body-sm text-on-surface">{source.site}</span>
                <span className="truncate font-mono text-label-sm text-outline">
                  {source.chapters != null ? `${source.chapters} chapters` : 'chapter count unknown'}
                </span>
              </div>
              <div className="flex shrink-0 items-center gap-space-xs">
                {best?.url === source.url && <Badge tone="secondary">Best</Badge>}
                <span className="font-mono text-label-sm text-outline">
                  {source.score.toFixed(2)}
                </span>
              </div>
            </div>
          ))
        )}
      </section>

      {writes.length > 0 && (
        <section className="flex flex-col gap-space-xs">
          <h3 className="font-mono text-label-sm uppercase tracking-wide text-outline">
            Written to
          </h3>
          {writes.map((write) => (
            <div key={write.target} className="flex flex-col gap-0.5">
              <div className="flex items-center justify-between gap-space-sm">
                <span className="text-body-sm text-on-surface">
                  {PROVIDER_LABEL[write.target] ?? write.target}
                </span>
                {/* Skipped is an absence, not a failure: MangaDex with no
                    personal credentials is the default setup and has nothing
                    to say to the user. */}
                {write.skipped ? (
                  <Badge tone="tertiary">Not configured</Badge>
                ) : write.ok ? (
                  <Badge tone="secondary">Written</Badge>
                ) : (
                  <Badge tone="error">Failed</Badge>
                )}
              </div>
              {write.error && (
                <span className="text-body-sm text-error">{write.error}</span>
              )}
              {write.at && (
                <span className="font-mono text-label-sm text-outline">
                  {relativeTime(write.at)}
                </span>
              )}
            </div>
          ))}
        </section>
      )}
    </DetailPanel>
  )
}
