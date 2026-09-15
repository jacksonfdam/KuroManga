import { Badge, Icon, StatusPill } from '../../ui'
import type { Series, SeriesMetadata } from '../../lib/api'
import { formatSeriesFormat } from '../../lib/format'

const PUBLICATION_LABEL: Record<string, string> = {
  releasing: 'Publishing',
  finished: 'Finished',
  not_yet_released: 'Not yet published',
  cancelled: 'Cancelled',
  hiatus: 'On hiatus',
}

/** "2020 — present", "2015 — 2021", or "2020" when only one year is known. */
function runYears(start: number | null, end: number | null): string | null {
  if (!start) return null
  if (!end) return `${start} — present`
  if (end === start) return `${start}`
  return `${start} — ${end}`
}

export function SeriesHeader({
  series,
  metadata,
  komgaBaseUrl,
}: {
  series: Series
  metadata: SeriesMetadata
  /** Where Komga is served to a browser. Empty means no link is offered. */
  komgaBaseUrl: string
}) {
  const format = formatSeriesFormat(series.format)
  const years = runYears(metadata.start_year, metadata.end_year)
  const credits = metadata.credits.slice(0, 3)

  return (
    <div className="flex min-w-0 flex-col gap-space-sm lg:col-span-9">
      {/* Only MyAnimeList names the magazine. A series synced from AniList
          alone has no breadcrumb, and the row is absent rather than empty. */}
      {metadata.publisher && (
        <p className="font-mono text-label-sm uppercase tracking-wide text-outline">
          {metadata.publisher}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {metadata.publication_status && (
          <Badge tone="secondary">{PUBLICATION_LABEL[metadata.publication_status]}</Badge>
        )}
        {years && <Badge tone="tertiary">{years}</Badge>}
        {metadata.demographic && <Badge tone="primary">{metadata.demographic}</Badge>}
        {metadata.country && (
          <span className="rounded bg-surface-container-high px-2 py-0.5 font-mono text-label-sm text-on-surface-variant">
            {metadata.country}
          </span>
        )}
        {format && <Badge tone="tertiary">{format}</Badge>}
        {series.status && <StatusPill status={series.status} />}
        {series.state === 'needs_review' && <Badge tone="error">Needs review</Badge>}
        {series.auto_download && <Badge tone="secondary">Auto-download active</Badge>}
        {/* The reader is Komga's, not this application's. Offered only once a
            scan has matched the series there and someone has said what address
            Komga answers on. */}
        {komgaBaseUrl && series.komga_series_id && (
          <a
            href={`${komgaBaseUrl}/series/${series.komga_series_id}`}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-full bg-primary/[0.12] px-space-sm py-0.5 font-mono text-label-sm text-primary transition-colors hover:bg-primary/20"
          >
            <Icon name="book" className="h-3.5 w-3.5" />
            Open in Komga
          </a>
        )}
      </div>

      {/* display-lg already carries weight 800 and -0.03em tracking, so a paired
          font-extrabold/tracking-tight would only fight it. */}
      <h1 className="flex flex-wrap items-baseline gap-space-md text-display-lg text-on-surface">
        {series.title}
        {metadata.native_title && metadata.native_title !== series.title && (
          <span className="text-headline-md text-on-surface-variant">
            {metadata.native_title}
          </span>
        )}
      </h1>

      {credits.length > 0 && (
        <p className="text-body-md text-on-surface-variant">
          {credits.map((credit, index) => (
            <span key={`${credit.role}-${credit.name}`}>
              {index > 0 && ' · '}
              {credit.role} by{' '}
              <span className="font-semibold text-on-surface">{credit.name}</span>
            </span>
          ))}
        </p>
      )}

      {series.genres.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {series.genres.map((genre) => (
            <span
              key={genre}
              className="rounded bg-surface-container-high px-2 py-0.5 font-mono text-label-sm text-on-surface-variant"
            >
              {genre}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
