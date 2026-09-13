import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { Badge, Button, Card, EmptyState, Icon, ProgressBar, Skeleton, StatusPill, Toggle } from '../../ui'
import { formatChapter, formatSeriesFormat, relativeTime } from '../../lib/format'
import { ChapterTable } from './ChapterTable'
import { MappingPanel } from './MappingPanel'
import { SyncTargets } from './SyncTargets'
import { totalChapters, useSeriesDetail } from './useSeriesDetail'

// Markup reference:
// .redesign/detalhes_do_mang_gest_o_de_pipeline_sincronia_multi_destino/code.html.
// The reference's header also carries a publisher/magazine breadcrumb, an
// author credit, a publication-status pill, a run-date range, a localisation
// flag, a "Salvar/Compartilhar" pair, a global score with a vote count, a
// personal star rating, a release cadence and a franchise ranking. None of
// that exists in this schema — series carries a title, slug, cover, format,
// genres, score (already 0-10) and the same downloaded/known/in_flight/failed
// counts the library card renders — so the header below shows exactly those
// and nothing invented to fill the silhouette.
export function SeriesDetailPage() {
  const { id } = useParams<{ id: string }>()
  const seriesId = Number(id)
  const { detail, notFound, reload, toggleAutoDownload, download, research } = useSeriesDetail(seriesId)

  if (notFound) {
    return (
      <EmptyState
        icon="warning"
        title="Series not found"
        detail="It may have been removed. Head back to the library and pick another one."
        action={
          <Link to="/library">
            <Button variant="surface" icon="book">
              Back to library
            </Button>
          </Link>
        }
      />
    )
  }

  if (!detail) {
    return (
      <div className="flex flex-col gap-space-lg">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    )
  }

  const { series, mapping, chapters, entries } = detail
  const total = totalChapters(detail)
  const format = formatSeriesFormat(series.format)

  return (
    <div className="flex flex-col gap-space-xl">
      <Link
        to="/library"
        className="flex w-fit items-center gap-space-xs text-body-sm text-on-surface-variant hover:text-on-surface"
      >
        <Icon name="chevron" className="h-4 w-4 rotate-90" />
        Back to library
      </Link>

      <section className="flex flex-col gap-space-lg sm:flex-row">
        <div className="aspect-[2/3] w-40 shrink-0 overflow-hidden rounded-lg bg-surface-container-highest shadow-card sm:w-48">
          {series.cover_url && (
            <img
              src={series.cover_url}
              alt={`Cover of ${series.title}`}
              className="h-full w-full object-cover"
            />
          )}
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-space-sm">
          <div className="flex flex-wrap items-center gap-2">
            {format && <Badge tone="tertiary">{format}</Badge>}
            {series.status && <StatusPill status={series.status} />}
            {series.state === 'needs_review' && <Badge tone="error">Needs review</Badge>}
            {series.auto_download && <Badge tone="secondary">Auto-download active</Badge>}
          </div>
          <h1 className="text-headline-lg font-extrabold tracking-tight text-on-surface">{series.title}</h1>
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
          <div className="flex flex-wrap items-center gap-space-md font-mono text-body-sm text-outline">
            {series.score !== null && <span className="text-tertiary">★ {series.score.toFixed(1)}</span>}
            <span>
              Ch {formatChapter(series.progress)}
              {total !== null && <span> / {total}</span>}
            </span>
            {series.updated_at && <span>Updated {relativeTime(series.updated_at)}</span>}
          </div>
          {total !== null && (
            <div className="max-w-sm">
              <ProgressBar value={series.progress} max={total} tone="secondary" />
            </div>
          )}
          <div className="flex flex-wrap gap-x-space-md gap-y-1 font-mono text-label-sm text-outline">
            <span>{series.downloaded} downloaded</span>
            <span>{series.known} known</span>
            {series.in_flight > 0 && <span className="text-tertiary">{series.in_flight} in flight</span>}
            {series.failed > 0 && <span className="text-error">{series.failed} failed</span>}
          </div>
        </div>
      </section>

      <div className="grid grid-cols-1 gap-space-lg lg:grid-cols-[1fr_320px]">
        <section className="flex flex-col gap-space-md">
          <h2 className="text-headline-md font-extrabold tracking-tight text-on-surface">Chapters</h2>
          <ChapterTable chapters={chapters} />
        </section>

        <aside className="flex flex-col gap-space-md">
          <MappingPanel mapping={mapping} onResearch={research} />
          <SyncTargets entries={entries} />
          <DownloadControls
            autoDownload={series.auto_download}
            onToggleAutoDownload={toggleAutoDownload}
            onDownload={download}
            onQueued={reload}
          />
        </aside>
      </div>
    </div>
  )
}

// Kept local rather than a fifth component file: it is two thin bindings
// around endpoints the library screen already exercises (setAutoDownload,
// download), not a piece of the reference's own layout. Reference shows an
// auto-computed "Batch Size 20: Caps 149-160" preview and a Komga rescan
// button; neither is a real number or endpoint this API exposes, so the
// range is a plain form instead of a precomputed silhouette.
function DownloadControls({
  autoDownload,
  onToggleAutoDownload,
  onDownload,
  onQueued,
}: {
  autoDownload: boolean
  onToggleAutoDownload: (enabled: boolean) => Promise<void>
  onDownload: (from?: number, to?: number) => Promise<{ queued: number }>
  onQueued: () => void
}) {
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [status, setStatus] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    setBusy(true)
    setStatus(null)
    try {
      const result = await onDownload(from ? Number(from) : undefined, to ? Number(to) : undefined)
      setStatus(
        result.queued > 0
          ? `Queued ${result.queued} chapter${result.queued === 1 ? '' : 's'}.`
          : 'Nothing to queue in that range.',
      )
      onQueued()
    } catch (error) {
      setStatus(String(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card as="section" elevated className="flex flex-col gap-space-sm">
      <h2 className="text-title-md text-on-surface">Downloads</h2>
      <Toggle
        checked={autoDownload}
        onChange={(checked) => {
          onToggleAutoDownload(checked).catch(() => undefined)
        }}
        label="Auto-download new chapters"
      />
      <div className="flex flex-col gap-space-xs border-t border-surface-container-highest/40 pt-space-sm">
        <span className="font-mono text-label-sm text-on-surface-variant">Download a range</span>
        <div className="flex items-center gap-space-xs">
          <input
            name="download-from-chapter"
            aria-label="From chapter"
            placeholder="From"
            inputMode="decimal"
            value={from}
            onChange={(event) => setFrom(event.target.value)}
            className="w-full rounded-lg bg-surface-container-lowest px-3 py-2 text-body-sm text-on-surface placeholder:text-outline focus:outline-none focus:ring-1 focus:ring-primary"
          />
          <input
            name="download-to-chapter"
            aria-label="To chapter"
            placeholder="To"
            inputMode="decimal"
            value={to}
            onChange={(event) => setTo(event.target.value)}
            className="w-full rounded-lg bg-surface-container-lowest px-3 py-2 text-body-sm text-on-surface placeholder:text-outline focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        <Button variant="primary" size="sm" icon="download" disabled={busy} onClick={submit} className="w-fit">
          Queue download
        </Button>
        {status && <p className="font-mono text-label-sm text-outline">{status}</p>}
      </div>
    </Card>
  )
}
