import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { Button, EmptyState, ErrorState, Icon, NoticeBar, Skeleton, Tabs } from '../../ui'
import { ChapterTable } from './ChapterTable'
import { CharacterGrid } from './CharacterGrid'
import { DownloadControls } from './DownloadControls'
import { MappingPanel } from './MappingPanel'
import { NotesPanel } from './NotesPanel'
import { ProgressManager } from './ProgressManager'
import { ScoreStrip } from './ScoreStrip'
import { SeriesHeader } from './SeriesHeader'
import { SimilarWorks } from './SimilarWorks'
import { SynopsisPanel } from './SynopsisPanel'
import { SyncTargets } from './SyncTargets'
import { totalChapters, useSeriesDetail } from './useSeriesDetail'

type Panel = 'chapters' | 'notes' | 'characters'

// The mockup's own geometry: a twelve-column hero with the cover on three,
// then a two-column body. What the mockup shows and this does not is listed in
// docs/superpowers/plans/2026-09-14-series-detail-complete.md — a weekday
// reading chart, a release cadence, per-chapter release dates and page counts,
// and a ComicInfo validation badge. None of them has a source, and an invented
// figure that fills a gap in a mockup is worse than the gap.
export function SeriesDetailPage() {
  const { id } = useParams<{ id: string }>()
  const seriesId = Number(id)
  const {
    detail,
    notFound,
    error,
    reload,
    toggleAutoDownload,
    download,
    research,
    setProgress,
    setListStatus,
    saveNotes,
  } = useSeriesDetail(seriesId)
  const [panel, setPanel] = useState<Panel>('chapters')

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

  const { series, metadata, mapping, chapters, entries } = detail
  const total = totalChapters(detail)

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
          background refresh says so here instead of collapsing to the
          not-found or first-load error screens above. */}
      {error && (
        <NoticeBar tone="error" text={`Couldn't refresh this series: ${error}`} onRetry={reload} />
      )}

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
        <SeriesHeader series={series} metadata={metadata} />
      </section>

      <ScoreStrip metadata={metadata} />

      <div className="grid grid-cols-1 gap-space-lg lg:grid-cols-[1fr_360px]">
        <div className="flex min-w-0 flex-col gap-space-lg">
          <ProgressManager
            detail={detail}
            total={total}
            minutesPerChapter={detail.reading_minutes_per_chapter}
            onProgress={setProgress}
            onStatus={setListStatus}
          />

          <section className="flex flex-col gap-space-md">
            <Tabs
              options={[
                { value: 'chapters', label: 'Chapters', count: chapters.length },
                { value: 'notes', label: 'Your note' },
                // A count only when the enrichment has landed; "(0)" while it
                // is still queued would read as "this manga has no characters".
                {
                  value: 'characters',
                  label: 'Characters',
                  count: metadata.characters.length || null,
                },
              ]}
              value={panel}
              onChange={setPanel}
            />
            <div hidden={panel !== 'chapters'}>
              <ChapterTable chapters={chapters} />
            </div>
            <div hidden={panel !== 'notes'}>
              {/* Mounted even while hidden: NotesPanel holds an unsaved draft in local
                  state, and unmounting the inactive tab would throw it away on a tab
                  click — the same loss the draft-preservation flag exists to prevent. */}
              <NotesPanel metadata={metadata} onSave={saveNotes} />
            </div>
            <div hidden={panel !== 'characters'}>
              <CharacterGrid characters={metadata.characters} />
            </div>
          </section>
        </div>

        <aside className="flex flex-col gap-space-md">
          <MappingPanel mapping={mapping} onResearch={research} />
          <SyncTargets entries={entries} />
          <DownloadControls
            autoDownload={series.auto_download}
            onToggleAutoDownload={toggleAutoDownload}
            onDownload={download}
            onQueued={reload}
          />
          <SynopsisPanel metadata={metadata} />
          <SimilarWorks items={metadata.similar} />
        </aside>
      </div>
    </div>
  )
}
