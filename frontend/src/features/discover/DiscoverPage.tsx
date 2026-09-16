import { useState } from 'react'
import { useOutletContext } from 'react-router-dom'

import { Button, EmptyState, ErrorState, NoticeBar, Skeleton } from '../../ui'
import type { DiscoverItem } from '../../lib/api'
import { DiscoverCard } from './DiscoverCard'
import { DiscoverDetail } from './DiscoverDetail'
import { PAGE_SIZE, useDiscover } from './useDiscover'

/**
 * Everything waiting on a decision, closest to done first.
 *
 * This replaces Discovery, Unmatched and Review, which were three screens
 * asking three stages of one question: is there a manga here you want, and
 * which one is it? An item carries what it still owes, and the order is what
 * makes one list of several hundred usable - most of it needs a manual search,
 * and without the ranking that buries everything that is one click away.
 */
export function DiscoverPage() {
  const { items, total, actionable, loaded, error, reload, notice, dismiss, offset, setOffset } =
    useDiscover()
  const [openItem, setOpenItem] = useState<DiscoverItem | null>(null)
  // Answering an item changes the nav badge, and dismissing one enqueues no
  // job — so without this the count beside Discover stays stale until
  // something unrelated fires a job event.
  const refreshShell = useOutletContext<() => void>()

  if (!loaded && error) {
    return <ErrorState title="Couldn't load Discover" detail={error} onRetry={reload} />
  }

  return (
    <div className="flex flex-col gap-space-lg">
      <div>
        <h1 className="text-headline-lg font-extrabold tracking-tight text-on-surface">Discover</h1>
        {/* Both numbers. The total alone reads as hopeless, and the actionable
            count alone hides how much is waiting behind it. */}
        <p className="mt-1 font-mono text-label-md text-outline">
          {actionable} you can answer now · {total} waiting in total
        </p>
      </div>

      {error && <NoticeBar tone="error" text={`Couldn't refresh: ${error}`} onRetry={reload} />}
      {notice && <NoticeBar tone={notice.tone} text={notice.text} />}

      {!loaded ? (
        <div className="grid grid-cols-2 gap-space-md sm:grid-cols-3 xl:grid-cols-5">
          {[0, 1, 2, 3, 4].map((slot) => (
            <Skeleton key={slot} className="aspect-[2/3] w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon="check"
          title="Nothing waiting"
          detail="Every anime on your lists has an answer, and every series has a source."
        />
      ) : (
        <div className={openItem ? 'grid grid-cols-1 gap-space-lg lg:grid-cols-[1fr_360px]' : ''}>
          <div className="flex min-w-0 flex-col gap-space-lg">
            <div className="grid grid-cols-2 gap-space-md sm:grid-cols-3 xl:grid-cols-5">
              {items.map((item) => (
                <DiscoverCard
                  key={`${item.kind}-${item.id}`}
                  item={item}
                  selected={openItem?.kind === item.kind && openItem?.id === item.id}
                  onOpen={() => setOpenItem(item)}
                />
              ))}
            </div>

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
          </div>

          {openItem && (
            <DiscoverDetail
              // Remounted per item, so a panel opened on one item never shows
              // the search results or fetched sources of the one before it.
              key={`${openItem.kind}-${openItem.id}`}
              item={openItem}
              onDone={() => {
                setOpenItem(null)
                void reload()
                refreshShell()
              }}
              onDismiss={() => {
                dismiss(openItem)
                setOpenItem(null)
                refreshShell()
              }}
              onClose={() => setOpenItem(null)}
            />
          )}
        </div>
      )}
    </div>
  )
}
