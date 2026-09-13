import { formatChapter, formatSeriesFormat } from '../../lib/format'
import type { Series } from '../../lib/api'
import { totalChapters } from './useLibrary'
import { QuickIncrement } from './QuickIncrement'

// Markup reference: the poster cards under "Leitura Ativa" in
// .redesign/biblioteca_principal_sincronizada_com_komga_provedores/code.html.
// The title sits below the art rather than over it — a long romanised title
// would otherwise cover the one piece of the card that identifies the manga.
export function CoverCard({
  series,
  onIncrement,
}: {
  series: Series
  onIncrement: (id: number, next: number) => Promise<void>
}) {
  const total = totalChapters(series)
  const pct = total ? Math.min(100, Math.round((series.progress / total) * 100)) : null
  const format = formatSeriesFormat(series.format)
  const genre = series.genres[0]
  const needsReview = series.state === 'needs_review'
  const extra = total ? total - series.progress : 0

  return (
    <div className="group flex flex-col transition-transform duration-300 hover:-translate-y-1 hover:shadow-glow">
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
        <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between p-2">
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
        <div className="absolute bottom-2 right-2">
          <QuickIncrement progress={series.progress} onIncrement={(next) => onIncrement(series.id, next)} />
        </div>
        <div className="absolute inset-x-0 bottom-0 h-1 bg-surface-container-lowest">
          <div className="h-full bg-primary transition-all duration-300" style={{ width: `${pct ?? 0}%` }} />
        </div>
      </div>
      <div className="flex flex-col gap-1 pt-2.5">
        <div className="flex items-center justify-between font-mono text-body-sm text-outline">
          <span className="truncate">{[format, genre].filter(Boolean).join(' • ') || ' '}</span>
          {pct !== null && <span className="shrink-0 text-secondary">{pct}%</span>}
        </div>
        <h3 className="truncate text-body-md font-bold text-on-surface transition-colors group-hover:text-primary">
          {series.title}
        </h3>
        <div className="flex items-center justify-between border-t border-surface-container-highest/40 pt-1.5 font-mono text-body-sm">
          <span className="text-on-surface">
            Ch {formatChapter(series.progress)}
            {total !== null && <span className="text-outline"> / {total}</span>}
          </span>
          {extra > 0 && <span className="text-secondary">+{extra} new</span>}
        </div>
      </div>
    </div>
  )
}
