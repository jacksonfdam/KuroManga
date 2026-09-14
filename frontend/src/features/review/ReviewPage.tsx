import { Button, EmptyState, ErrorState, NoticeBar, Skeleton } from '../../ui'
import { CandidateCard } from './CandidateCard'
import { useReview } from './useReview'

// No mockup depicts this screen. The two-column layout (a fixed series panel
// beside a candidate list) is built from the library screen's own patterns —
// a cover-and-metadata aside like ContinueReading's rows, cards with the same
// radius/shadow/tint vocabulary as CoverCard — rather than a reference render.
export function ReviewPage({ onResolved }: { onResolved: () => void }) {
  const { waiting, current, loaded, error, reload, notice, manualUrl, setManualUrl, busy, confirm, search } =
    useReview(onResolved)

  if (!loaded && error) {
    return <ErrorState title="Couldn't load the review queue" detail={error} onRetry={reload} />
  }

  if (!loaded) {
    return (
      <div className="grid grid-cols-1 gap-space-lg lg:grid-cols-[320px_1fr]">
        <Skeleton className="h-96 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    )
  }

  // "Nothing waiting" is a claim about the pipeline — every series has a
  // confirmed source — so it is only ever shown when the queue genuinely came
  // back empty. A failed load renders above, never as this.
  if (!current) {
    return (
      <div className="flex flex-col gap-space-lg">
        {error && <NoticeBar tone="error" text={`Couldn't refresh the queue: ${error}`} onRetry={reload} />}
        <EmptyState
          icon="check"
          title="Nothing waiting"
          detail="Every series has a confirmed source. New matches land here after the next sync."
        />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-space-lg">
      <div>
        <h1 className="text-headline-lg font-extrabold tracking-tight text-on-surface">Review</h1>
        <p className="mt-1 font-mono text-label-md text-outline">
          {waiting.length} waiting · press{' '}
          <kbd className="rounded bg-surface-container-high px-1 py-0.5 text-on-surface">1</kbd>–
          <kbd className="rounded bg-surface-container-high px-1 py-0.5 text-on-surface">9</kbd> to confirm a
          candidate
        </p>
      </div>

      {error && <NoticeBar tone="error" text={`Couldn't refresh the queue: ${error}`} onRetry={reload} />}
      {notice && <NoticeBar tone={notice.tone} text={notice.text} />}

      <div className="grid grid-cols-1 gap-space-lg lg:grid-cols-[320px_1fr]">
        <aside className="flex h-fit flex-col gap-space-md rounded-xl bg-surface-container-low p-space-lg shadow-card">
          <div className="aspect-[2/3] w-full overflow-hidden rounded-lg bg-surface-container-highest">
            {current.series.cover_url && (
              <img
                src={current.series.cover_url}
                alt={`Cover of ${current.series.title}`}
                className="h-full w-full object-cover"
              />
            )}
          </div>
          <div>
            <h2 className="text-title-md text-on-surface">{current.series.title}</h2>
            <div className="mt-1 flex flex-col gap-0.5 font-mono text-label-sm text-outline">
              {[...new Set([...current.series.english, ...current.series.romaji])]
                .filter(Boolean)
                .map((title) => (
                  <span key={title} className="truncate">
                    {title}
                  </span>
                ))}
            </div>
          </div>

          <div className="flex flex-col gap-space-xs border-t border-surface-container-highest/40 pt-space-md">
            <label htmlFor="manual-url" className="font-mono text-label-sm text-on-surface-variant">
              Paste a source URL instead
            </label>
            <input
              id="manual-url"
              value={manualUrl}
              placeholder="https://mangadex.org/title/..."
              onChange={(event) => setManualUrl(event.target.value)}
              className="w-full rounded-lg bg-surface-container-lowest px-3 py-2 text-body-sm text-on-surface placeholder:text-outline focus:outline-none focus:ring-1 focus:ring-primary"
            />
            <Button variant="primary" disabled={!manualUrl || busy} onClick={() => confirm(manualUrl)}>
              Confirm this URL
            </Button>
          </div>

          <Button variant="surface" icon="sync" disabled={busy} onClick={search}>
            Search again
          </Button>
        </aside>

        <section className="flex flex-col gap-space-sm">
          {current.candidates.length === 0 ? (
            <EmptyState
              icon="search"
              title="No candidates found"
              detail="Paste the source URL on the left, or search again."
            />
          ) : (
            current.candidates.map((candidate, index) => (
              <CandidateCard
                key={candidate.id}
                candidate={candidate}
                index={index}
                disabled={busy}
                onConfirm={() => confirm(candidate.source_url)}
              />
            ))
          )}
        </section>
      </div>
    </div>
  )
}
