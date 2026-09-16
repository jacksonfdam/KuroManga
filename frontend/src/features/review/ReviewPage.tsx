import { Button, EmptyState, ErrorState, NoticeBar, SegmentedControl, Skeleton } from '../../ui'
import { CandidateCard } from './CandidateCard'
import { QueueGrid } from './QueueGrid'
import { QueueList, type QueueProps } from './QueueList'
import { useReview, type QueueLayout, type ReviewView } from './useReview'

// No mockup depicts this screen. The two-column layout (a fixed series panel
// beside a candidate list) is built from the library screen's own patterns —
// a cover-and-metadata aside like ContinueReading's rows, cards with the same
// radius/shadow/tint vocabulary as CoverCard — rather than a reference render.
//
// The tabs, and the undo that rides on the notice bar, are Unmatched's: that
// screen already answers "put this one aside, and let me take it back" and the
// two should teach each other rather than each invent a shape.

// The same two options, and the same two icons, the library offers — this is
// one control the user learns once.
const LAYOUTS: { value: QueueLayout; icon: 'grid' | 'list'; label: string }[] = [
  { value: 'grid', icon: 'grid', label: 'Grid' },
  { value: 'list', icon: 'list', label: 'List' },
]

/** One queue, drawn whichever way the user asked for. Both layouts take the
    same props, so choosing between them is the only thing this decides. */
function Queue({ layout, ...props }: QueueProps & { layout: QueueLayout }) {
  return layout === 'grid' ? <QueueGrid {...props} /> : <QueueList {...props} />
}

export function ReviewPage({ onResolved }: { onResolved: () => void }) {
  const {
    view,
    setView,
    layout,
    setLayout,
    order,
    ignored,
    skipped,
    position,
    at,
    current,
    loaded,
    candidatesLoaded,
    error,
    candidatesError,
    reload,
    reloadCandidates,
    notice,
    undo,
    manualUrl,
    setManualUrl,
    busy,
    confirm,
    skip,
    ignore,
    unignore,
    goTo,
    next,
    previous,
    search,
  } = useReview(onResolved)

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

  const total = order.length
  const options: { value: ReviewView; label: string }[] = [
    { value: 'reviewing', label: 'Reviewing' },
    { value: 'queue', label: `Queue · ${total}` },
    { value: 'ignored', label: `Ignored · ${ignored.length}` },
  ]

  const subline =
    view === 'queue'
      ? 'Everything waiting, in the order Review will ask. Anything you skipped sits at the end.'
      : view === 'ignored'
        ? 'Series you told Review to stop asking about. They stay in your library and on your lists — nothing is deleted and nothing stops syncing. With no source mapped, nothing downloads either.'
        : total === 0
          ? 'Nothing is waiting for a source.'
          : null

  return (
    <div className="flex flex-col gap-space-lg">
      <div>
        <h1 className="text-headline-lg font-extrabold tracking-tight text-on-surface">Review</h1>
        {subline ? (
          <p className="mt-1 font-mono text-label-md text-outline">{subline}</p>
        ) : (
          <p className="mt-1 font-mono text-label-md text-outline">
            {position + 1} of {total} waiting · press{' '}
            <kbd className="rounded bg-surface-container-high px-1 py-0.5 text-on-surface">1</kbd>–
            <kbd className="rounded bg-surface-container-high px-1 py-0.5 text-on-surface">9</kbd> to
            confirm a candidate,{' '}
            <kbd className="rounded bg-surface-container-high px-1 py-0.5 text-on-surface">
              Shift+S
            </kbd>{' '}
            to skip,{' '}
            <kbd className="rounded bg-surface-container-high px-1 py-0.5 text-on-surface">
              Shift+I
            </kbd>{' '}
            to stop asking
          </p>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-space-md">
        <SegmentedControl options={options} value={view} onChange={setView} />
        {/* Only where there is a list to lay out. The one-at-a-time view is a
            single series, which is neither a grid nor rows. */}
        {view !== 'reviewing' && (
          <SegmentedControl options={LAYOUTS} value={layout} onChange={setLayout} />
        )}
      </div>

      {error && <NoticeBar tone="error" text={`Couldn't refresh the queue: ${error}`} onRetry={reload} />}
      {notice && (
        <NoticeBar
          tone={notice.tone}
          text={notice.text}
          onRetry={undo ?? undefined}
          actionLabel="Undo"
        />
      )}

      {view === 'queue' &&
        (total === 0 ? (
          <EmptyState
            icon="check"
            title="Nothing waiting"
            detail="Every series has a confirmed source. New matches land here after the next sync."
          />
        ) : (
          <Queue
            layout={layout}
            items={order}
            position={position}
            skipped={skipped}
            busy={busy}
            onPick={goTo}
            onUnignore={null}
          />
        ))}

      {view === 'ignored' &&
        (ignored.length === 0 ? (
          <EmptyState
            icon="search"
            title="Nothing ignored"
            detail="Anything you mark Not interested waits here. Put one back and Review asks about it again."
          />
        ) : (
          <Queue
            layout={layout}
            items={ignored}
            position={null}
            skipped={skipped}
            busy={busy}
            onPick={null}
            onUnignore={unignore}
          />
        ))}

      {view === 'reviewing' &&
        // "Nothing waiting" is a claim about the pipeline — every series has a
        // confirmed source — so it is only ever drawn from a queue that loaded
        // and came back empty. A failed load renders above, never as this.
        (!at ? (
          <EmptyState
            icon="check"
            title="Nothing waiting"
            detail="Every series has a confirmed source. New matches land here after the next sync."
          />
        ) : (
          <>
            {/* The queue's own controls, above both columns: they act on the
                queue rather than on either the series or its candidates. */}
            <div className="flex flex-wrap items-center justify-between gap-space-md">
              <div className="flex items-center gap-space-sm">
                <Button
                  variant="surface"
                  size="sm"
                  disabled={position === 0}
                  onClick={previous}
                >
                  Previous
                </Button>
                <span className="font-mono text-label-md text-on-surface-variant">
                  {position + 1} / {total}
                </span>
                <Button
                  variant="surface"
                  size="sm"
                  disabled={position >= total - 1}
                  onClick={next}
                >
                  Next
                </Button>
              </div>
              <div className="flex flex-wrap items-center gap-space-sm">
                {/* Disabled at a queue of one, where "move it behind the
                    others" has no others to move it behind. */}
                <Button variant="surface" disabled={busy || total < 2} onClick={skip}>
                  Skip
                </Button>
                <Button variant="danger" disabled={busy} onClick={() => void ignore()}>
                  Not interested
                </Button>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-space-lg lg:grid-cols-[320px_1fr]">
              <aside className="flex h-fit flex-col gap-space-md rounded-xl bg-surface-container-low p-space-lg shadow-card">
                {/* Drawn from the queue row until the candidates land, so
                    moving between two series never blanks the panel that says
                    which series you are looking at. */}
                <div className="aspect-[2/3] w-full overflow-hidden rounded-lg bg-surface-container-highest">
                  {(current?.series.cover_url ?? at.cover_url) && (
                    <img
                      src={current?.series.cover_url ?? at.cover_url ?? ''}
                      alt={`Cover of ${current?.series.title ?? at.title}`}
                      className="h-full w-full object-cover"
                    />
                  )}
                </div>
                <div>
                  <h2 className="text-title-md text-on-surface">
                    {current?.series.title ?? at.title}
                  </h2>
                  <div className="mt-1 flex flex-col gap-0.5 font-mono text-label-sm text-outline">
                    {current &&
                      [...new Set([...current.series.english, ...current.series.romaji])]
                        .filter(Boolean)
                        .map((title) => (
                          // Same reason as the candidate card: these variants
                          // differ in their tails, so a single truncated line
                          // shows the reader the half they already agree on.
                          <span key={title} className="line-clamp-2">
                            {title}
                          </span>
                        ))}
                  </div>
                </div>

                <div className="flex flex-col gap-space-xs border-t border-surface-container-highest/40 pt-space-md">
                  <label
                    htmlFor="manual-url"
                    className="font-mono text-label-sm text-on-surface-variant"
                  >
                    Paste a source URL instead
                  </label>
                  <input
                    id="manual-url"
                    value={manualUrl}
                    placeholder="https://mangadex.org/title/..."
                    onChange={(event) => setManualUrl(event.target.value)}
                    className="w-full rounded-lg bg-surface-container-lowest px-3 py-2 text-body-sm text-on-surface placeholder:text-outline focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                  <Button
                    variant="primary"
                    disabled={!manualUrl || busy}
                    onClick={() => void confirm(manualUrl)}
                  >
                    Confirm this URL
                  </Button>
                </div>

                <Button variant="surface" icon="sync" disabled={busy} onClick={search}>
                  Search again
                </Button>
              </aside>

              <section className="flex flex-col gap-space-sm">
                {candidatesError && (
                  <NoticeBar
                    tone="error"
                    text={`Couldn't load candidates for ${at.title}: ${candidatesError}`}
                    onRetry={reloadCandidates}
                  />
                )}
                {!candidatesLoaded && !candidatesError ? (
                  <Skeleton className="h-40 w-full" />
                ) : current && current.candidates.length === 0 ? (
                  <EmptyState
                    icon="search"
                    title="No candidates found"
                    detail="Paste the source URL on the left, or search again. If no source carries this title, skip it to the end of the queue — or mark it Not interested, which takes it out of Review for good and leaves the series in your library."
                  />
                ) : (
                  current?.candidates.map((candidate, index) => (
                    <CandidateCard
                      key={candidate.id}
                      candidate={candidate}
                      index={index}
                      disabled={busy}
                      onConfirm={() => void confirm(candidate.source_url)}
                    />
                  ))
                )}
              </section>
            </div>
          </>
        ))}
    </div>
  )
}
