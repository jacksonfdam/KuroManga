import { useCallback, useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'

import { Button, EmptyState, ErrorState, NoticeBar, Skeleton } from '../../ui'
import { SuggestionCard } from './SuggestionCard'
import { SuggestionDetail } from './SuggestionDetail'
import { WriteFailures } from './WriteFailures'
import { useDiscovery } from './useDiscovery'

// No reference render exists for this screen. The product brief lists Discovery
// among its six designed screens, but no Discovery folder was ever exported —
// Home, Library, Series detail, Stats and Settings are the five that were. So
// the layout is built from DESIGN.md's poster-grid rules and the card
// vocabulary the library screen already establishes, not from a mockup.
export function DiscoveryPage() {
  const refreshShell = useOutletContext<() => void>()
  const {
    items,
    total,
    writeFailures,
    loaded,
    error,
    reload,
    notice,
    busy,
    settingFor,
    setStatus,
    setDownload,
    add,
    dismiss,
    refresh,
  } = useDiscovery(refreshShell)

  const [selectedId, setSelectedId] = useState<number | null>(null)
  // Approving or dismissing a suggestion mutates it in place, so the panel
  // reads the current entry out of the list on every render rather than
  // holding a copy that would go stale the moment the card beside it changed.
  const selected = items.find((item) => item.id === selectedId) ?? null
  const closeDetail = useCallback(() => setSelectedId(null), [])

  if (!loaded && error) {
    return <ErrorState title="Couldn't load suggestions" detail={error} onRetry={reload} />
  }

  return (
    <div className="flex flex-col gap-space-lg">
      <div className="flex flex-wrap items-end justify-between gap-space-md">
        <div>
          <h1 className="text-headline-lg font-extrabold tracking-tight text-on-surface">
            Discovery
          </h1>
          <p className="mt-1 font-mono text-label-md text-outline">
            {/* The route pages at 100, so the count says what is on screen and
                what is waiting rather than passing one off as the other. */}
            {items.length < total ? `Showing ${items.length} of ${total}. ` : ''}
            Manga the anime on your lists is based on.{' '}
            <Link to="/unmatched" className="text-primary hover:underline">
              Anime with no match
            </Link>{' '}
            need a search by hand.
          </p>
        </div>
        <Button variant="surface" icon="search" onClick={refresh}>
          Search now
        </Button>
      </div>

      {error && (
        <NoticeBar tone="error" text={`Couldn't refresh suggestions: ${error}`} onRetry={reload} />
      )}
      {notice && <NoticeBar tone={notice.tone} text={notice.text} />}

      {!loaded ? (
        <div className="grid grid-cols-2 gap-space-md sm:grid-cols-3 xl:grid-cols-5">
          {[0, 1, 2, 3, 4].map((slot) => (
            <Skeleton key={slot} className="aspect-[2/5] w-full" />
          ))}
        </div>
      ) : (
        <div className={selected ? 'grid grid-cols-1 gap-space-lg lg:grid-cols-[1fr_360px]' : ''}>
          <div className="flex min-w-0 flex-col gap-space-lg">
            <WriteFailures items={writeFailures} />
            {items.length === 0 ? (
              <EmptyState
                icon="sparkle"
                title="Nothing new"
                detail="Every anime on your lists already has a manga match, or you have answered for the ones that did not."
              />
            ) : (
              <div className="grid grid-cols-2 gap-space-md sm:grid-cols-3 xl:grid-cols-5">
                {items.map((item) => (
                  <SuggestionCard
                    key={item.id}
                    item={item}
                    choice={settingFor(item)}
                    busy={busy === item.id}
                    selected={selectedId === item.id}
                    onSelect={() => setSelectedId(item.id)}
                    onStatus={(status) => setStatus(item, status)}
                    onDownload={(download) => setDownload(item, download)}
                    onAdd={() => add(item)}
                    onDismiss={() => dismiss(item)}
                  />
                ))}
              </div>
            )}
          </div>

          {selected && <SuggestionDetail suggestion={selected} onClose={closeDetail} />}
        </div>
      )}
    </div>
  )
}
