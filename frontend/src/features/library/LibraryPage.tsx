import { EmptyState, ErrorState, Icon, NoticeBar, SegmentedControl, Skeleton } from '../../ui'
import { STATUS_LABEL } from '../../lib/format'
import { ContinueReading } from './ContinueReading'
import { SeriesGrid } from './SeriesGrid'
import { SeriesTable } from './SeriesTable'
import { StatusTabs } from './StatusTabs'
import { useLibrary } from './useLibrary'

// Markup reference:
// .redesign/biblioteca_principal_sincronizada_com_komga_provedores/code.html.
//
// Four of its widgets are dropped, for the same reason the Settings and Series
// detail screens record their own omissions: no field behind them.
//
//  - The sub-header strip's storage figure ("1.84 TB / 4.0 TB (ZFS Pool)").
//    Nothing in this API reports pool capacity or usage; the worker writes CBZ
//    files to a path and never measures the volume under it.
//  - The Komga audit line ("54 séries mapeadas, 98 no catálogo, 4.280 capítulos
//    em CBZ"). /api/series counts what this database knows; it does not ask
//    Komga what its own catalogue holds, so two of those three numbers have no
//    source and the third would be a different number wearing the same label.
//  - The worker/queue telemetry beside it ("Worker #4: IDLE", "Queue: 0
//    pendentes", "Taxa de Acerto Metadata: 99.4%", the next cron countdown).
//    /api/jobs/counts has pending and leased totals, but not per-worker
//    liveness, not a metadata hit rate, and not a next-fire time.
//  - The "Ritmo de Leitura da Semana" panel ("48 capítulos nos últimos 7 dias",
//    a peak weekday, "+18% vs. semana anterior"). Progress is stored as a
//    current chapter per entry, not as dated reading events, so no window of
//    any length can be computed from it.
//
// An invented figure that fills a gap in a mockup is worse than the gap.
export function LibraryPage() {
  const { series, all, loaded, error, status, setStatus, view, setView, query, setQuery, increment, reload, continueReading, notice } =
    useLibrary()

  // Nothing has ever arrived and the request failed: an empty library and an
  // unreachable API are different facts, and telling the user to go and
  // connect a provider when the truth is that the fetch failed sends them to
  // fix a screen that is already correct.
  if (!loaded && error) {
    return <ErrorState title="Couldn't load the library" detail={error} onRetry={reload} />
  }

  if (!loaded) {
    return (
      <div className="flex flex-col gap-space-lg">
        <Skeleton className="h-16 w-full" />
        <div className="grid grid-cols-2 gap-space-md sm:grid-cols-3 lg:grid-cols-5">
          {[0, 1, 2, 3, 4].map((slot) => (
            <Skeleton key={slot} className="aspect-[2/3] w-full" />
          ))}
        </div>
      </div>
    )
  }

  // The banner rides along with the empty state too: a library that is empty
  // *and* failing to refresh would otherwise show only the "run a sync" copy,
  // which is the same misdirection one level down.
  if (all.length === 0) {
    return (
      <div className="flex flex-col gap-space-lg">
        {error && <NoticeBar tone="error" text={`Couldn't refresh the library: ${error}`} onRetry={reload} />}
        <EmptyState
          icon="book"
          title="Nothing in the library yet"
          detail="Connect a list in Settings and run a sync — series show up here once MyAnimeList or AniList has something to read."
        />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-space-xl">
      {error && <NoticeBar tone="error" text={`Couldn't refresh the library: ${error}`} onRetry={reload} />}
      {notice && <NoticeBar tone={notice.tone} text={notice.text} />}
      <section className="flex flex-col gap-space-md">
        <div className="flex flex-wrap items-center justify-between gap-space-md rounded-2xl bg-surface-container-low p-2 shadow-card">
          <StatusTabs all={all} status={status} onChange={setStatus} />
          <SegmentedControl
            options={[
              { value: 'grid', icon: 'grid', label: 'Grid' },
              { value: 'table', icon: 'list', label: 'Table' },
            ]}
            value={view}
            onChange={setView}
          />
        </div>
        <div className="rounded-xl bg-surface-container/60 p-3.5 backdrop-blur-md">
          <div className="relative w-full sm:w-72">
            <span className="pointer-events-none absolute left-3 top-2.5 text-outline">
              <Icon name="search" className="h-4 w-4" />
            </span>
            <input
              name="library-filter"
              aria-label="Filter by title"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Filter by title..."
              className="w-full rounded-lg bg-surface-container-low py-2 pl-9 pr-4 text-body-sm text-on-surface placeholder:text-outline focus:bg-surface-container focus:outline-none"
            />
          </div>
        </div>
      </section>

      <ContinueReading series={continueReading} onIncrement={increment} />

      <section className="flex flex-col gap-space-md">
        <div className="flex flex-wrap items-baseline justify-between gap-space-sm">
          <div className="flex items-baseline gap-space-sm">
            <h2 className="text-headline-md font-extrabold tracking-tight text-on-surface">
              {status === 'all' ? 'All series' : status === 'reading' ? 'Active reading' : `${STATUS_LABEL[status]} series`}
            </h2>
            <span className="font-mono text-label-md text-outline">
              Showing {series.length} of {all.length} series
            </span>
          </div>
          {view === 'grid' && (
            <span className="font-mono text-label-sm uppercase tracking-wider text-outline">Auto-fill grid</span>
          )}
        </div>
        {series.length === 0 ? (
          <EmptyState
            icon="search"
            title="No matches"
            detail="Nothing in this status matches the current filter. Try another tab or clear the search."
          />
        ) : view === 'grid' ? (
          <SeriesGrid series={series} onIncrement={increment} />
        ) : (
          <SeriesTable series={series} onIncrement={increment} />
        )}
      </section>
    </div>
  )
}
