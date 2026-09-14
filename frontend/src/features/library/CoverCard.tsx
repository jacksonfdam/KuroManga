import { Link } from 'react-router-dom'

import { Icon, QuickIncrement } from '../../ui'
import { formatChapter, formatProviders, formatSeriesFormat } from '../../lib/format'
import type { Series } from '../../lib/api'
import { totalChapters } from './useLibrary'

// Markup reference: the poster cards under "Leitura Ativa" in
// .redesign/biblioteca_principal_sincronizada_com_komga_provedores/code.html.
// The title sits below the art rather than over it — a long romanised title
// would otherwise cover the one piece of the card that identifies the manga.
export function CoverCard({
  series,
  pending = false,
  onIncrement,
  selected = false,
  onToggleSelect,
}: {
  series: Series
  /** The chapter shown is one the queue took and no worker has written yet. */
  pending?: boolean
  onIncrement: (id: number, next: number) => Promise<void>
  /** Marked for a bulk action: a violet ring and a badge say so. */
  selected?: boolean
  onToggleSelect?: (id: number) => void
}) {
  const total = totalChapters(series)
  const pct = total ? Math.min(100, Math.round((series.progress / total) * 100)) : null
  const format = formatSeriesFormat(series.format)
  const genre = series.genres[0]
  const needsReview = series.state === 'needs_review'
  const extra = total ? total - series.progress : 0
  const pipeline = pipelineNote(series)

  return (
    <Link
      to={`/series/${series.id}`}
      className={`group relative flex flex-col transition-transform duration-300 hover:-translate-y-1 hover:shadow-glow ${
        selected ? 'rounded-lg ring-2 ring-violet-500 shadow-xl shadow-violet-500/20' : ''
      }`}
    >
      {onToggleSelect && (
        // Inside the Link, so the box has to refuse the navigation the card
        // otherwise performs on any click within it.
        <button
          type="button"
          role="checkbox"
          aria-checked={selected}
          aria-label={selected ? `Deselect ${series.title}` : `Select ${series.title}`}
          onClick={(event) => {
            event.preventDefault()
            event.stopPropagation()
            onToggleSelect(series.id)
          }}
          className={`absolute left-2 top-2 z-10 flex h-6 w-6 items-center justify-center rounded-md border backdrop-blur-md transition-colors ${
            selected
              ? 'border-violet-400 bg-violet-600 text-white'
              : 'border-outline-variant/50 bg-surface-container-lowest/90 text-transparent hover:border-violet-400'
          }`}
        >
          <Icon name="check" className="text-[1rem]" />
        </button>
      )}
      <div
        className={`relative aspect-[2/3] w-full overflow-hidden rounded-lg border bg-surface-container-highest ${
          needsReview ? 'border-error/40' : 'border-white/[0.08]'
        }`}
      >
        {series.cover_url && (
          <img
            src={series.cover_url}
            alt={`Cover of ${series.title}`}
            className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.03]"
          />
        )}
        <div className="pointer-events-none absolute inset-x-0 top-0 flex flex-col gap-1 p-2">
          <div className="flex items-start justify-between gap-1">
            {needsReview ? (
              <span className="rounded bg-error-container/80 px-1.5 py-0.5 font-mono text-label-sm font-bold text-error backdrop-blur-md">
                Needs review
              </span>
            ) : format ? (
              <span className="rounded bg-surface-container-lowest/85 px-1.5 py-0.5 font-mono text-label-sm font-bold text-on-surface-variant backdrop-blur-md">
                {format}
              </span>
            ) : (
              <span />
            )}
            {series.score !== null && (
              <span className="rounded bg-surface-container-lowest/85 px-1.5 py-0.5 font-mono text-label-sm font-bold text-tertiary backdrop-blur-md">
                ★ {series.score.toFixed(1)}
              </span>
            )}
          </div>
          {series.providers.length > 0 && (
            <span className="w-fit rounded bg-surface-container-lowest/85 px-1.5 py-0.5 font-mono text-label-sm text-primary backdrop-blur-md">
              {formatProviders(series.providers)} sync
            </span>
          )}
        </div>
        {/* Stops the click from bubbling to the card's own Link — the quick-add
            button and "open this series" are two different actions stacked on
            the same corner of the art. */}
        <div className="absolute bottom-2 right-2" onClick={(event) => event.preventDefault()}>
          <QuickIncrement
            progress={series.progress}
            pending={pending}
            onIncrement={(next) => onIncrement(series.id, next)}
          />
        </div>
        {/* 4px, flush with the image's own bottom edge — DESIGN.md's Manga Cover
            Cards spec, not the card's outer rounded corner. */}
        <div className="absolute inset-x-0 bottom-0 h-1 bg-surface-container-lowest">
          <div className="h-full bg-secondary transition-all duration-300" style={{ width: `${pct ?? 0}%` }} />
        </div>
      </div>
      <div className="flex flex-col gap-1 pt-2.5">
        <div className="flex items-center justify-between font-mono text-body-sm text-outline">
          <span className="truncate">{[format, genre].filter(Boolean).join(' • ') || ' '}</span>
          {pct !== null && <span className={`shrink-0 ${pct >= 80 ? 'text-secondary' : 'text-primary'}`}>{pct}%</span>}
        </div>
        <h3 className="truncate text-body-md font-bold text-on-surface transition-colors group-hover:text-primary">
          {series.title}
        </h3>
        {pipeline && (
          <div className={`flex items-center gap-1.5 font-mono text-label-sm ${pipeline.tone}`}>
            <Icon name={pipeline.icon} className="h-3 w-3" />
            <span className="truncate">{pipeline.text}</span>
          </div>
        )}
        <div className="flex items-center justify-between border-t border-surface-container-highest/40 pt-1.5 font-mono text-body-sm">
          <span className="text-on-surface">
            Ch {formatChapter(series.progress)}
            {total !== null && <span className="text-outline"> / {total}</span>}
            {/* The tinted button is a hover-sized target on a poster grid and
                easy to miss; the word is what says the number is not the
                providers' yet. */}
            {pending && <span className="text-tertiary"> · syncing</span>}
          </span>
          {extra > 0 ? (
            <span className="text-secondary">+{extra} new</span>
          ) : total !== null ? (
            <Icon name="check" className="h-4 w-4 text-secondary" />
          ) : null}
        </div>
      </div>
    </Link>
  )
}

// What this line says is picked from whichever real signal the series has —
// never a made-up "not downloaded yet" filler when there is nothing to report.
function pipelineNote(
  series: Series,
): { text: string; icon: 'warning' | 'download' | 'check' | 'sync'; tone: string } | null {
  if (series.state === 'needs_review') {
    return { text: 'Needs a source mapping', icon: 'warning', tone: 'text-error' }
  }
  if (series.auto_download) {
    return { text: 'Auto-download active', icon: 'download', tone: 'text-secondary' }
  }
  if (series.downloaded > 0) {
    return { text: `${series.downloaded} chapters downloaded`, icon: 'check', tone: 'text-outline' }
  }
  if (series.source_site) {
    return { text: `Mapped to ${series.source_site}`, icon: 'sync', tone: 'text-primary' }
  }
  return null
}
