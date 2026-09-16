import { ConfirmDialog, EmptyState, ErrorState, Icon, NoticeBar, SegmentedControl, Skeleton } from '../../ui'
import { STATUS_LABEL } from '../../lib/format'
import type { ListStatus } from '../../lib/format'
import { api } from '../../lib/api'
import { useEffect, useState } from 'react'
import { ContinueReading } from './ContinueReading'
import { BatchActionBar } from './BatchActionBar'
import { SeriesGrid } from './SeriesGrid'
import { SeriesTable } from './SeriesTable'
import { StatusTabs } from './StatusTabs'
import { useLibrary } from './useLibrary'
import { useSelection } from './useSelection'

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
  const { series, all, loaded, error, status, setStatus, view, setView, query, setQuery, increment, reload, continueReading, pending, notice } =
    useLibrary()
  const selection = useSelection()
  const [applying, setApplying] = useState(false)
  const [batchNotice, setBatchNotice] = useState<string | null>(null)
  const [confirmingRemove, setConfirmingRemove] = useState(false)
  const [removing, setRemoving] = useState(false)

  // A selection restored from the session describes the library as it was when
  // the tab was opened. Anything answered in Review, or dropped by a sync,
  // since then is gone from `all` and has to leave the selection with it, or
  // the action bar offers to act on more than it can reach.
  const { retain } = selection
  useEffect(() => {
    if (loaded) retain(all.map((row) => row.id))
  }, [all, loaded, retain])

  // The rows settle from the job stream the library already listens to, so the
  // reload here is for the status the API has recorded, not for the writes —
  // those land later and announce themselves.
  const applyBatch = async (next: ListStatus) => {
    setApplying(true)
    try {
      const result = await api.batchStatus(selection.ids, next)
      const skipped = result.skipped.length
      setBatchNotice(
        `Queued ${result.queued} ${result.queued === 1 ? 'title' : 'titles'} as ${STATUS_LABEL[next]}` +
          (skipped ? `. ${skipped} skipped — not on any reading list.` : '.'),
      )
      selection.clear()
      await reload()
    } catch (failure) {
      setBatchNotice(`Couldn't queue the batch: ${String(failure)}`)
    } finally {
      setApplying(false)
    }
  }

  const removeSelected = async () => {
    setRemoving(true)
    try {
      const result = await api.removeSeries(selection.ids)
      setBatchNotice(
        `Removed ${result.removed} ${result.removed === 1 ? 'series' : 'series'}. ` +
          'A list sync will not bring them back.',
      )
      selection.clear()
      setConfirmingRemove(false)
      await reload()
    } catch (failure) {
      setBatchNotice(`Couldn't remove: ${String(failure)}`)
    } finally {
      setRemoving(false)
    }
  }

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
      {selection.count > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 self-end rounded-lg border border-primary/40 bg-primary/10 p-1">
          <span className="flex items-center gap-1.5 rounded-md bg-primary px-2.5 py-1 text-label-sm font-semibold text-on-primary">
            <Icon name="check_box" className="text-[1rem]" />
            <span>Selection mode</span>
            <span className="rounded-full bg-on-primary/20 px-1.5 font-mono text-label-sm font-bold">
              {selection.count} selected
            </span>
          </span>
          <button
            type="button"
            onClick={selection.clear}
            className="rounded-md px-2 py-1 font-mono text-label-sm text-outline transition-colors hover:bg-surface-container-high hover:text-on-surface"
          >
            Clear
          </button>
          <button
            type="button"
            onClick={() => selection.selectAll(series.map((row) => row.id))}
            className="rounded-md px-2 py-1 font-mono text-label-sm text-outline transition-colors hover:bg-surface-container-high hover:text-on-surface"
            title="Select every series currently shown"
          >
            Select all shown
          </button>
        </div>
      )}
      {error && <NoticeBar tone="error" text={`Couldn't refresh the library: ${error}`} onRetry={reload} />}
      {notice && <NoticeBar tone={notice.tone} text={notice.text} />}
      {batchNotice && <NoticeBar tone="info" text={batchNotice} />}
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

      <ContinueReading series={continueReading} pending={pending} onIncrement={increment} />

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
          <SeriesGrid
            series={series}
            pending={pending}
            onIncrement={increment}
            selected={selection.selected}
            onToggleSelect={selection.toggle}
          />
        ) : (
          <SeriesTable
            series={series}
            pending={pending}
            onIncrement={increment}
            selected={selection.selected}
            onToggleSelect={selection.toggle}
          />
        )}
      </section>

      {confirmingRemove && (
        <ConfirmDialog
          title={`Remove ${selection.count} ${selection.count === 1 ? 'series' : 'series'}?`}
          consequences={[
            'Anything queued for them is cancelled.',
            'Chapters already downloaded stay on disk and in Komga.',
            'A list sync will not bring them back.',
            'Your MyAnimeList and AniList entries are left as they are.',
          ]}
          confirmLabel={removing ? 'Removing…' : 'Remove'}
          busy={removing}
          onConfirm={() => void removeSelected()}
          onCancel={() => setConfirmingRemove(false)}
        />
      )}

      {selection.count > 0 && (
        <BatchActionBar
          count={selection.count}
          busy={applying}
          onApply={applyBatch}
          onRemove={() => setConfirmingRemove(true)}
          onCancel={selection.clear}
        />
      )}
    </div>
  )
}
