import { EmptyState, Icon, SegmentedControl } from '../../ui'
import { ContinueReading } from './ContinueReading'
import { SeriesGrid } from './SeriesGrid'
import { SeriesTable } from './SeriesTable'
import { StatusTabs } from './StatusTabs'
import { useLibrary } from './useLibrary'

export function LibraryPage() {
  const { series, all, status, setStatus, view, setView, query, setQuery, increment, continueReading } = useLibrary()

  if (all.length === 0) {
    return (
      <EmptyState
        icon="book"
        title="Nothing in the library yet"
        detail="Connect a list in Settings and run a sync — series show up here once MyAnimeList or AniList has something to read."
      />
    )
  }

  return (
    <div className="flex flex-col gap-space-xl">
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
        <div className="relative w-full sm:w-80">
          <span className="pointer-events-none absolute left-3 top-2.5 text-outline">
            <Icon name="search" className="h-4 w-4" />
          </span>
          <input
            name="library-filter"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Filter by title..."
            className="w-full rounded-lg bg-surface-container-low py-2 pl-9 pr-4 text-body-sm text-on-surface placeholder:text-outline focus:bg-surface-container focus:outline-none"
          />
        </div>
      </section>

      <ContinueReading series={continueReading} onIncrement={increment} />

      <section className="flex flex-col gap-space-md">
        <div className="flex items-baseline gap-space-sm">
          <h2 className="text-headline-md font-extrabold tracking-tight text-on-surface">
            {status === 'all' ? 'All series' : 'Active reading'}
          </h2>
          <span className="font-mono text-label-md text-outline">
            Showing {series.length} of {all.length} series
          </span>
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
