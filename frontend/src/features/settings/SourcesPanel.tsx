import { Button, Card, EmptyState, ErrorState, NoticeBar, Skeleton } from '../../ui'
import { SourceRow } from './SourceRow'
import { useSources } from './useSources'

// Language codes the catalogue actually carries today. Hardcoding a list the
// API does not serve would be inventing a figure, so this stays the two
// languages the seeded rows use plus "any" — it grows when the generator lands
// and the API can report the set.
const LANGUAGES = [
  { value: '', label: 'Any language' },
  { value: 'en', label: 'English' },
  { value: 'ja', label: 'Japanese' },
]

export function SourcesPanel() {
  const {
    items,
    total,
    page,
    size,
    loaded,
    error,
    reload,
    notice,
    busy,
    query,
    lang,
    search,
    filterLanguage,
    setPage,
    toggle,
  } = useSources()

  const pages = Math.max(1, Math.ceil(total / size))

  return (
    <Card elevated className="flex flex-col gap-space-md">
      <div className="flex flex-wrap items-center justify-between gap-space-sm">
        <div>
          <h3 className="text-title-md text-on-surface">Sources</h3>
          <p className="text-body-sm text-on-surface-variant">
            The sites searched when a series needs a match. A site that cannot run says why.
          </p>
        </div>
        {loaded && (
          <span className="font-mono text-label-sm text-on-surface-variant">
            {items.length} of {total}
          </span>
        )}
      </div>

      <div className="flex flex-wrap gap-space-sm">
        <input
          type="search"
          aria-label="Search sources"
          placeholder="Search by name or key"
          value={query}
          onChange={(event) => search(event.target.value)}
          className="min-w-0 flex-1 rounded-lg bg-surface-container-lowest px-space-md py-space-sm text-body-md text-on-surface shadow-inner focus:outline-none focus:ring-2 focus:ring-primary"
        />
        <select
          aria-label="Filter by language"
          value={lang}
          onChange={(event) => filterLanguage(event.target.value)}
          className="rounded-lg bg-surface-container-lowest px-space-md py-space-sm text-body-md text-on-surface shadow-inner focus:outline-none focus:ring-2 focus:ring-primary"
        >
          {LANGUAGES.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      {notice && <NoticeBar tone={notice.tone} text={notice.text} />}

      {/* A refresh that failed over a loaded page is not the same fact as a
          first request that failed, and the page on screen is still real. */}
      {error && loaded && <NoticeBar tone="error" text={error} onRetry={reload} />}

      {!loaded && !error && (
        <div className="flex flex-col gap-space-sm">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      )}

      {!loaded && error && <ErrorState detail={error} onRetry={reload} />}

      {loaded && items.length === 0 && (
        <EmptyState
          icon="search"
          title="No source matches"
          // Not "no sources exist": the filters are the reason, and saying the
          // other thing sends the user to look for a broken catalogue.
          detail="No site in the catalogue matches this search and language."
        />
      )}

      {loaded && items.length > 0 && (
        <div className="flex flex-col">
          {items.map((source) => (
            <SourceRow
              key={source.key}
              source={source}
              busy={busy === source.key}
              onToggle={() => toggle(source)}
            />
          ))}
        </div>
      )}

      {loaded && pages > 1 && (
        <div className="flex items-center justify-between gap-space-sm">
          <Button
            variant="surface"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            Previous
          </Button>
          <span className="font-mono text-label-sm text-on-surface-variant">
            Page {page} of {pages}
          </span>
          <Button
            variant="surface"
            disabled={page >= pages}
            onClick={() => setPage(page + 1)}
          >
            Next
          </Button>
        </div>
      )}
    </Card>
  )
}
