import { Icon } from '../../ui'
import type { Series, SeriesState } from '../../lib/api'
import { PROVIDER_LABEL, formatChapter, formatSeriesFormat } from '../../lib/format'
import { totalChapters } from './useLibrary'
import { useIncrementFlash, type FlashState } from './useIncrementFlash'

// The stepper's own flash colours — small and flat, unlike QuickIncrement's
// bordered glass button, so it keeps its own literal map rather than
// borrowing one built for a different surface (ProgressBar/Badge/StatusPill
// each do the same: one tone map per visual context).
const FLASH: Record<NonNullable<FlashState>, string> = {
  success: 'bg-secondary text-on-secondary',
  error: 'bg-error text-on-error',
}

// The reference's fifth column is "Status Pipeline": what the pipeline is
// doing with this series. This table showed the reading status instead, which
// is already the filter sitting directly above it — so the row said the same
// thing twice and never said whether a series was mapped, downloading, or
// waiting for a human.
const STATE_LABEL: Record<SeriesState, string> = {
  mapped: 'Mapped',
  needs_review: 'Needs review',
  downloading: 'Downloading',
  failed: 'Failed',
}

// Bracket form again: 12 is not on Tailwind's opacity scale (see StatusPill).
const STATE_TINT: Record<SeriesState, string> = {
  mapped: 'bg-secondary/[0.12] text-secondary',
  needs_review: 'bg-warning/[0.12] text-warning',
  downloading: 'bg-tertiary/[0.12] text-tertiary',
  failed: 'bg-error/[0.12] text-error',
}

// Markup reference: "Modo Tabela Rápida" in
// .redesign/biblioteca_principal_sincronizada_com_komga_provedores/code.html.
function SeriesRow({
  row,
  index,
  onIncrement,
}: {
  row: Series
  index: number
  onIncrement: (id: number, next: number) => Promise<void>
}) {
  const total = totalChapters(row)
  const pct = total ? Math.min(100, Math.round((row.progress / total) * 100)) : 0
  const format = formatSeriesFormat(row.format)
  const { flash, busy, trigger } = useIncrementFlash((next) => onIncrement(row.id, next))

  return (
    <tr className="h-16 transition-colors hover:bg-surface-container">
      <td className="px-3 text-center font-mono text-outline">{String(index + 1).padStart(2, '0')}</td>
      {/* max-w-0 is what lets the title truncate: a table cell is otherwise
          as wide as its longest word, and one 90-character light-novel title
          pushed the pipeline column off the right edge. */}
      <td className="max-w-0 px-4">
        <div className="flex items-center gap-3">
          <div className="h-14 w-10 shrink-0 overflow-hidden rounded-lg bg-surface-container-highest shadow-sm">
            {row.cover_url && <img src={row.cover_url} alt="" className="h-full w-full object-cover" />}
          </div>
          <div className="flex min-w-0 flex-col">
            <span className="truncate font-semibold text-on-surface">{row.title}</span>
            <span className="truncate font-mono text-label-sm text-outline">
              {[format, row.genres[0]].filter(Boolean).join(' • ') || '—'}
            </span>
          </div>
        </div>
      </td>
      <td className="px-3">
        <div className="flex flex-wrap gap-1">
          {row.providers.length === 0 ? (
            <span className="font-mono text-label-sm text-outline">—</span>
          ) : (
            row.providers.map((provider) => (
              <span key={provider} className="rounded bg-primary/10 px-1.5 py-0.5 font-mono text-label-sm text-primary">
                {PROVIDER_LABEL[provider] ?? provider}
              </span>
            ))
          )}
        </div>
      </td>
      <td className="px-3">
        {/* Where the chapters come from, which the reference puts beside the
            list providers and this table left out entirely. It is not the same
            fact as the providers column: those are the reading lists, this is
            the site the CBZ files are pulled from. */}
        {row.source_site ? (
          row.source_url ? (
            <a
              href={row.source_url}
              target="_blank"
              rel="noreferrer"
              className="font-mono text-label-sm text-secondary hover:underline"
            >
              {PROVIDER_LABEL[row.source_site] ?? row.source_site}
            </a>
          ) : (
            <span className="font-mono text-label-sm text-secondary">
              {PROVIDER_LABEL[row.source_site] ?? row.source_site}
            </span>
          )
        ) : (
          <span className="font-mono text-label-sm text-outline">Not mapped</span>
        )}
      </td>
      <td className="px-4">
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-1.5 font-mono text-body-sm">
            {/*
              The reference table shows a minus here too. It is left out on
              purpose: the API's forward-only guard refuses any write that
              would not advance the lowest-progress provider entry, and for
              a single-provider series the displayed number *is* that
              minimum — so a decrement is rejected with 409 every time, not
              on some edge case. Lowering a reader's recorded progress isn't
              an operation the API exposes at all; the product brief treats
              that as inviolable. Do not re-add this control from the
              mockup without a write path that can actually accept it.
            */}
            <span className="font-bold text-on-surface">{formatChapter(row.progress)}</span>
            <button
              type="button"
              onClick={() => trigger(row.progress + 1)}
              disabled={busy}
              aria-label="Mark next chapter read"
              className={`flex h-5 w-5 items-center justify-center rounded font-bold text-on-primary-container transition-colors disabled:cursor-not-allowed ${
                flash ? FLASH[flash] : 'bg-primary/20 hover:bg-primary hover:text-on-primary'
              }`}
            >
              <Icon name="add" className="h-3 w-3" />
            </button>
            {total !== null && <span className="text-outline">/ {total}</span>}
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-container-highest">
            <div className="h-full rounded-full bg-secondary" style={{ width: `${pct}%` }} />
          </div>
        </div>
      </td>
      <td className="px-3">
        <span
          className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-space-sm py-0.5 font-mono text-label-sm ${STATE_TINT[row.state]}`}
        >
          <span className="h-1.5 w-1.5 rounded-full bg-current" />
          {STATE_LABEL[row.state]}
        </span>
      </td>
    </tr>
  )
}

export function SeriesTable({
  series,
  onIncrement,
}: {
  series: Series[]
  onIncrement: (id: number, next: number) => Promise<void>
}) {
  return (
    <div className="w-full overflow-x-auto rounded-xl bg-surface-container-low shadow-card">
      <table className="w-full min-w-[820px] border-collapse text-left">
        <thead>
          <tr className="bg-surface-container font-mono text-label-sm uppercase tracking-wider text-outline">
            <th className="w-10 px-3 py-3 text-center">#</th>
            <th className="w-full px-4 py-3">Title</th>
            <th className="w-40 px-3 py-3">Lists</th>
            <th className="w-28 px-3 py-3">Chapter source</th>
            <th className="w-52 px-4 py-3">Progress</th>
            <th className="w-36 px-3 py-3">Pipeline</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-surface-container-highest/20 text-body-sm">
          {series.map((row, index) => (
            <SeriesRow key={row.id} row={row} index={index} onIncrement={onIncrement} />
          ))}
        </tbody>
      </table>
    </div>
  )
}
