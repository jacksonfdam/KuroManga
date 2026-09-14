import { Link, useParams } from 'react-router-dom'

import { Badge, Button, EmptyState, ErrorState, Icon, NoticeBar, ProgressBar, Skeleton, StatusPill } from '../../ui'
import { formatChapter, formatSeriesFormat, relativeTime } from '../../lib/format'
import { ChapterTable } from './ChapterTable'
import { DownloadControls } from './DownloadControls'
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
  const { detail, notFound, error, reload, toggleAutoDownload, download, research } =
    useSeriesDetail(seriesId)

  // A 404 is the only case worth replacing the screen for — the series
  // itself is gone. Any other failure (a dropped connection, a 500) is
  // handled below, where it must not throw away a page already on screen.
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

  // The first load failed and there is nothing to fall back to yet.
  if (!detail && error) {
    return <ErrorState title="Couldn't load this series" detail={error} onRetry={reload} />
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

      {/* A page already showing real data stays showing it — a failed
          background refresh (e.g. the reload DownloadControls fires after
          queuing) says so here instead of collapsing to the not-found or
          first-load error screens above, which would throw the page away
          over a transient failure. */}
      {error && <NoticeBar tone="error" text={`Couldn't refresh this series: ${error}`} onRetry={reload} />}

      {/* The reference's own hero geometry: a twelve-column grid, the cover on
          three of them (about 270px at the 1280 the mockups were rendered at,
          not the 192 this started with) and the text on the other nine. */}
      <section className="grid grid-cols-1 items-start gap-space-xl lg:grid-cols-12">
        <div className="aspect-[2/3] w-56 shrink-0 overflow-hidden rounded-xl bg-surface-container-highest shadow-card sm:w-64 lg:col-span-3 lg:w-full">
          {series.cover_url && (
            <img
              src={series.cover_url}
              alt={`Cover of ${series.title}`}
              className="h-full w-full object-cover"
            />
          )}
        </div>
        <div className="flex min-w-0 flex-col gap-space-sm lg:col-span-9">
          <div className="flex flex-wrap items-center gap-2">
            {format && <Badge tone="tertiary">{format}</Badge>}
            {series.status && <StatusPill status={series.status} />}
            {series.state === 'needs_review' && <Badge tone="error">Needs review</Badge>}
            {series.auto_download && <Badge tone="secondary">Auto-download active</Badge>}
          </div>
          {/* display-lg, as the reference render's own title is. The scale
              already carries weight 800 and -0.03em tracking, so a paired
              font-extrabold/tracking-tight would only fight it. */}
          <h1 className="text-display-lg text-on-surface">{series.title}</h1>
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
          <div className="flex flex-wrap items-center gap-space-md font-mono text-label-md text-outline">
            {series.score !== null && <span className="text-tertiary">★ {series.score.toFixed(1)}</span>}
            <span>
              Ch {formatChapter(series.progress)}
              {total !== null && <span> / {total}</span>}
            </span>
            {series.updated_at && <span>Updated {relativeTime(series.updated_at)}</span>}
          </div>
          {total !== null && (
            // The reference's hero runs the full nine columns; a sm-width bar
            // under a display-lg title is what made this header read light.
            <div className="max-w-xl">
              <ProgressBar value={series.progress} max={total} tone="secondary" />
            </div>
          )}
          <div className="flex flex-wrap gap-x-space-md gap-y-1 font-mono text-label-md text-outline">
            <span>{series.downloaded} downloaded</span>
            <span>{series.known} known</span>
            {series.in_flight > 0 && <span className="text-tertiary">{series.in_flight} in flight</span>}
            {series.failed > 0 && <span className="text-error">{series.failed} failed</span>}
          </div>
        </div>
      </section>

      <div className="grid grid-cols-1 gap-space-lg lg:grid-cols-[1fr_320px]">
        <section className="flex flex-col gap-space-md">
          {/* The count belongs in the heading, as the reference's own
              "Capítulos & Histórico (172)" puts it: the table below is bounded,
              so the heading is where the total is stated. */}
          <h2 className="text-headline-md font-extrabold tracking-tight text-on-surface">
            Chapters {chapters.length > 0 && <span className="font-mono text-outline">({chapters.length})</span>}
          </h2>
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
