import { Link, useLocation } from 'react-router-dom'

import { Icon, ProgressBar, QuickIncrement } from '../../ui'
import type { ContinueReadingEntry } from '../../lib/api'
import { originState } from '../../lib/backTo'
import { formatChapter } from '../../lib/format'

/**
 * The mockup puts a source label ("MangaDex", "Comick") over each cover here.
 * /api/dashboard's continue_reading rows carry no mapping, so there is nothing
 * to put in it and it is left out rather than guessed at — the chip that is
 * rendered instead says how many chapters are already on disk, which is a fact
 * the payload does carry and the one that decides whether you can read now.
 */
function Entry({
  row,
  pending,
  onIncrement,
}: {
  row: ContinueReadingEntry
  /** The chapter shown is queued and not yet written to the lists. */
  pending: boolean
  onIncrement: (seriesId: number, next: number) => Promise<void>
}) {
  const total = row.total_chapters
  // Home links straight into a series, so "back" has to mean Home rather than
  // the library the detail screen used to assume.
  const location = useLocation()

  return (
    <article className="flex gap-space-md rounded-xl bg-surface-container-low p-space-md shadow-card">
      <Link
        to={`/series/${row.series_id}`}
        state={originState(location)}
        className="h-28 w-20 shrink-0 overflow-hidden rounded-lg bg-surface-container-highest shadow-sm"
      >
        {row.cover_url && (
          <img src={row.cover_url} alt={`Cover of ${row.title}`} loading="lazy" className="h-full w-full object-cover" />
        )}
      </Link>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex flex-wrap items-center gap-space-xs">
          {row.downloaded_ahead > 0 && (
            <span className="rounded-full bg-secondary/[0.12] px-space-sm py-0.5 font-mono text-label-sm text-secondary">
              {row.downloaded_ahead} on disk
            </span>
          )}
          <span
            className={`rounded-full px-space-sm py-0.5 font-mono text-label-sm ${
              row.in_komga ? 'bg-tertiary/[0.12] text-tertiary' : 'bg-surface-container-high text-outline'
            }`}
          >
            {row.in_komga ? 'In Komga' : 'Not in Komga'}
          </span>
        </div>

        <h3 className="mt-1 truncate text-body-md font-bold text-on-surface" title={row.title}>
          <Link
            to={`/series/${row.series_id}`}
            state={originState(location)}
            className="hover:underline"
          >
            {row.title}
          </Link>
        </h3>

        <p className="mt-0.5 font-mono text-label-md text-on-surface-variant">
          Chapter {formatChapter(row.progress)}
          {total !== null && <span className="text-outline"> of {total}</span>}
        </p>

        {/* A bar needs a denominator. Nothing said how long this manga is, so
            there is no share of it to draw. */}
        {total !== null && (
          <div className="mt-space-sm">
            <ProgressBar value={row.progress} max={total} tone="secondary" />
          </div>
        )}

        <div className="mt-auto flex items-center gap-space-sm pt-space-sm">
          <QuickIncrement
            progress={row.progress}
            pending={pending}
            writable={row.writable}
            onIncrement={(next) => onIncrement(row.series_id, next)}
          />
          {/* The label carries the state: the button's own tint is the quiet
              half of it, and this row is where a user watches the number they
              just changed. */}
          {pending ? (
            <span className="font-mono text-label-sm text-tertiary">Syncing…</span>
          ) : (
            <span className="font-mono text-label-sm text-outline">+1 chapter</span>
          )}
          {row.chapters_remaining !== null && (
            <span className="ml-auto shrink-0 font-mono text-label-sm text-outline">
              {row.chapters_remaining === 0
                ? 'Up to date'
                : `${row.chapters_remaining} left`}
            </span>
          )}
        </div>
      </div>
    </article>
  )
}

export function ContinueReading({
  rows,
  active,
  pending,
  onIncrement,
}: {
  rows: ContinueReadingEntry[]
  /** Every series being read, not just the ones on this row: the payload caps
      the cards at eight and the heading must not pass its page off as a total. */
  active: number
  /** Series whose last +1 is queued and not yet written. */
  pending: ReadonlySet<number>
  onIncrement: (seriesId: number, next: number) => Promise<void>
}) {
  return (
    <section className="flex flex-col gap-space-md">
      <div className="flex flex-wrap items-center gap-space-sm">
        <Icon name="book" className="h-5 w-5 text-primary" />
        <h2 className="text-headline-md font-extrabold tracking-tight text-on-surface">
          Continue reading
        </h2>
        <span className="rounded bg-surface-container-high px-space-sm py-0.5 font-mono text-label-sm text-outline">
          {active} active
        </span>
        <Link to="/library" className="ml-auto font-mono text-label-md text-primary hover:underline">
          See all in Library
        </Link>
      </div>

      {rows.length === 0 ? (
        <p className="rounded-xl bg-surface-container-low px-space-md py-space-md text-body-sm text-on-surface-variant">
          Nothing is being read right now. Set a series to Reading on MyAnimeList or AniList and
          it turns up here after the next sync.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-space-md md:grid-cols-2 xl:grid-cols-4">
          {rows.map((row) => (
            <Entry
              key={row.series_id}
              row={row}
              pending={pending.has(row.series_id)}
              onIncrement={onIncrement}
            />
          ))}
        </div>
      )}
    </section>
  )
}
