import { useState } from 'react'
import { useOutletContext } from 'react-router-dom'

import {
  Chip,
  EmptyState,
  ErrorState,
  NoticeBar,
  Pager,
  SearchField,
  SelectField,
  Skeleton,
} from '../../ui'
import type { DiscoverItem, DiscoverKind, DiscoverSort } from '../../lib/api'
import { DiscoverCard } from './DiscoverCard'
import { DiscoverDetail } from './DiscoverDetail'
import { KIND_LABEL } from './labels'
import { DEFAULT_PER, PER_CHOICES, useDiscover } from './useDiscover'

const KINDS: DiscoverKind[] = ['suggestion', 'review', 'unmatched']

const SORT_OPTIONS: { value: DiscoverSort; label: string }[] = [
  { value: 'rank', label: 'Closest to done' },
  { value: 'title', label: 'Title A–Z' },
  { value: '-title', label: 'Title Z–A' },
  { value: '-added', label: 'Newest first' },
  { value: 'added', label: 'Oldest first' },
]

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
  const {
    items, total, actionable, pages, loaded, error, reload, notice, dismiss,
    query, setQuery, kinds, toggleKind, sort, setSort, page, setPage, per, setPer,
  } = useDiscover()
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
        {/* Both numbers, and both counted after the filters: the total alone
            reads as hopeless, the actionable count alone hides how much is
            waiting behind it, and either one taken over the whole feed would
            describe a screen the reader is not on. */}
        <p className="mt-1 font-mono text-label-md text-outline">
          {actionable} you can answer now · {total} waiting in total
        </p>
      </div>

      <section className="flex flex-wrap items-center gap-space-md rounded-xl bg-surface-container/60 p-3.5 backdrop-blur-md">
        <SearchField
          name="discover-filter"
          label="Filter by title"
          value={query}
          onChange={setQuery}
          placeholder="Filter by title..."
        />
        <div className="flex flex-wrap items-center gap-space-xs">
          {KINDS.map((kind) => (
            <Chip key={kind} active={kinds.includes(kind)} onClick={() => toggleKind(kind)}>
              {KIND_LABEL[kind]}
            </Chip>
          ))}
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-space-md">
          <SelectField label="Sort" value={sort} options={SORT_OPTIONS} onChange={setSort} />
          <SelectField
            label="Per page"
            value={String(per)}
            options={PER_CHOICES.map((size) => ({ value: String(size), label: String(size) }))}
            onChange={(next) => setPer(Number(next) || DEFAULT_PER)}
          />
        </div>
      </section>

      {error && <NoticeBar tone="error" text={`Couldn't refresh: ${error}`} onRetry={reload} />}
      {notice && <NoticeBar tone={notice.tone} text={notice.text} />}

      {!loaded ? (
        <div className="grid grid-cols-2 gap-space-md sm:grid-cols-3 xl:grid-cols-5">
          {[0, 1, 2, 3, 4].map((slot) => (
            <Skeleton key={slot} className="aspect-[2/3] w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        // Two different facts. Nothing is waiting at all, or nothing is waiting
        // that answers this filter — and telling a reader their queue is clear
        // when they have simply typed a title that matches none of it is a lie
        // they would act on.
        <EmptyState
          icon={total === 0 && !query && kinds.length === 0 ? 'check' : 'search'}
          title={total === 0 && !query && kinds.length === 0 ? 'Nothing waiting' : 'Nothing here'}
          detail={
            total === 0 && !query && kinds.length === 0
              ? 'Every anime on your lists has an answer, and every series has a source.'
              : total === 0
                ? 'No item matches these filters.'
                : `This page is past the end of ${total} matching items.`
          }
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

            <Pager page={page} pages={pages} total={total} per={per} onPage={setPage} />
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

      {/* The pager stays reachable when the grid is empty but the feed is not:
          a stale link to page 9 of a list that has shrunk has to have a way
          back, and the grid above is not it. */}
      {loaded && items.length === 0 && total > 0 && (
        <Pager page={page} pages={pages} total={total} per={per} onPage={setPage} />
      )}
    </div>
  )
}
