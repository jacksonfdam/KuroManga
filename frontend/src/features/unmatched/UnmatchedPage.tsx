import { useCallback, useState } from 'react'
import { useOutletContext } from 'react-router-dom'

import { Button, EmptyState, ErrorState, NoticeBar, SegmentedControl, Skeleton } from '../../ui'
import { AnimeRow } from './AnimeRow'
import { UnmatchedDetail } from './UnmatchedDetail'
import { PAGE_SIZE, useUnmatched } from './useUnmatched'

// No reference render exists for this screen: it postdates the product brief
// entirely, so nothing was ever designed for it. The row-plus-disclosure shape
// below follows the library table's row conventions and the review screen's
// candidate cards rather than a mockup.
export function UnmatchedPage() {
  const refreshShell = useOutletContext<() => void>()
  const {
    items,
    total,
    loaded,
    error,
    reload,
    notice,
    undo,
    offset,
    setOffset,
    typed,
    setTyped,
    filter,
    showHidden,
    swapView,
    results,
    searching,
    busy,
    search,
    settingFor,
    setStatus,
    setDownload,
    add,
    setHidden,
  } = useUnmatched(refreshShell)

  const [selectedId, setSelectedId] = useState<number | null>(null)
  // Derived rather than stored: a row can leave the list by being hidden,
  // added, filtered or paged away, and holding the object would keep the
  // panel open describing something that is no longer on screen. One rule
  // covers every case, including the ones nobody has written yet.
  const selected = items.find((anime) => anime.id === selectedId) ?? null
  const closeDetail = useCallback(() => setSelectedId(null), [])

  if (!loaded && error) {
    return <ErrorState title="Couldn't load the unmatched list" detail={error} onRetry={reload} />
  }

  return (
    <div className="flex flex-col gap-space-lg">
      <div>
        <h1 className="text-headline-lg font-extrabold tracking-tight text-on-surface">
          Anime with no match
        </h1>
        <p className="mt-1 font-mono text-label-md text-outline">
          {filter
            ? `${total} ${showHidden ? 'hidden anime' : 'anime'} matching “${filter}”. The whole list is filtered, not the page you are on.`
            : showHidden
              ? 'The anime you hid, listed on their own. Unhide one to put it back where it can be searched.'
              : `${total} anime on your lists that no relation could turn into a manga. Nothing is searched until you ask for it.`}
        </p>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-space-md">
        <SegmentedControl
          options={[
            { value: 'open', label: 'Without a match' },
            { value: 'hidden', label: 'Hidden' },
          ]}
          value={showHidden ? 'hidden' : 'open'}
          onChange={(value) => swapView(value === 'hidden')}
        />
        <div className="flex min-w-0 flex-1 justify-end">
          <input
            type="search"
            aria-label="Filter anime by title"
            placeholder="Filter by title"
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            className="w-full max-w-xs rounded-lg bg-surface-container-lowest px-space-md py-space-sm text-body-sm text-on-surface placeholder:text-outline focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
      </div>

      {error && <NoticeBar tone="error" text={`Couldn't refresh the list: ${error}`} onRetry={reload} />}
      {notice && (
        <NoticeBar
          tone={notice.tone}
          text={notice.text}
          onRetry={undo ?? undefined}
          actionLabel="Undo"
        />
      )}

      <div className={selected ? 'grid grid-cols-1 gap-space-lg lg:grid-cols-[1fr_360px]' : ''}>
        <div className="flex min-w-0 flex-col gap-space-lg">
          {!loaded ? (
            <div className="flex flex-col gap-space-md">
              {[0, 1, 2].map((slot) => (
                <Skeleton key={slot} className="h-28 w-full" />
              ))}
            </div>
          ) : items.length === 0 ? (
            <EmptyState
              icon="search"
              title={filter ? 'Nothing matches that' : showHidden ? 'Nothing hidden' : 'Nothing left'}
              detail={
                filter
                  ? `Nothing matches “${filter}”. Every spelling an anime is known by is read, so try part of another one.`
                  : showHidden
                    ? 'Anything you hide on the other tab waits here.'
                    : 'Every anime on your lists has a manga match or is hidden.'
              }
            />
          ) : (
            <div className="flex flex-col gap-space-md">
              {items.map((anime) => (
                <AnimeRow
                  key={anime.id}
                  anime={anime}
                  found={results[anime.id]}
                  searching={searching === anime.id}
                  busy={busy}
                  showHidden={showHidden}
                  selected={selectedId === anime.id}
                  settingFor={settingFor}
                  onSearch={() => search(anime)}
                  onHide={() => setHidden(anime, !showHidden)}
                  onSelect={() => setSelectedId(anime.id)}
                  onStatus={setStatus}
                  onDownload={setDownload}
                  onAdd={(candidate) => add(anime, candidate)}
                />
              ))}
            </div>
          )}

          {items.length > 0 && (
            <div className="flex flex-wrap items-center gap-space-md">
              <Button
                variant="surface"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                Previous
              </Button>
              <Button
                variant="surface"
                disabled={offset + PAGE_SIZE >= total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                Next
              </Button>
              <span className="font-mono text-label-sm text-outline">
                {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
              </span>
            </div>
          )}
        </div>

        {selected && <UnmatchedDetail anime={selected} onClose={closeDetail} />}
      </div>
    </div>
  )
}
