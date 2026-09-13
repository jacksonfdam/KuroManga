import { Icon, StatusPill } from '../../ui'
import type { Series } from '../../lib/api'
import { PROVIDER_LABEL, formatChapter, formatSeriesFormat } from '../../lib/format'
import { totalChapters } from './useLibrary'

// Markup reference: "Modo Tabela Rápida" in
// .redesign/biblioteca_principal_sincronizada_com_komga_provedores/code.html.
// The +/- pair calls the same `increment` the grid's quick-add button does —
// this view trades the poster for density, not for a second write path.
export function SeriesTable({
  series,
  onIncrement,
}: {
  series: Series[]
  onIncrement: (id: number, next: number) => Promise<void>
}) {
  return (
    <div className="w-full overflow-x-auto rounded-xl bg-surface-container-low shadow-card">
      <table className="w-full min-w-[640px] border-collapse text-left">
        <thead>
          <tr className="bg-surface-container font-mono text-label-sm uppercase tracking-wider text-outline">
            <th className="w-10 px-3 py-3 text-center">#</th>
            <th className="px-4 py-3">Title</th>
            <th className="w-40 px-3 py-3">Sources</th>
            <th className="w-52 px-4 py-3">Progress</th>
            <th className="w-32 px-3 py-3">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-surface-container-highest/20 text-body-sm">
          {series.map((row, index) => {
            const total = totalChapters(row)
            const pct = total ? Math.min(100, Math.round((row.progress / total) * 100)) : 0
            const format = formatSeriesFormat(row.format)
            return (
              <tr key={row.id} className="h-16 transition-colors hover:bg-surface-container">
                <td className="px-3 text-center font-mono text-outline">{String(index + 1).padStart(2, '0')}</td>
                <td className="px-4">
                  <div className="flex items-center gap-3">
                    <div className="h-14 w-10 shrink-0 overflow-hidden rounded-lg bg-surface-container-highest shadow-sm">
                      {row.cover_url && (
                        <img src={row.cover_url} alt="" className="h-full w-full object-cover" />
                      )}
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
                        <span
                          key={provider}
                          className="rounded bg-primary/10 px-1.5 py-0.5 font-mono text-label-sm text-primary"
                        >
                          {PROVIDER_LABEL[provider] ?? provider}
                        </span>
                      ))
                    )}
                  </div>
                </td>
                <td className="px-4">
                  <div className="flex flex-col gap-1.5">
                    <div className="flex items-center gap-1.5 font-mono text-body-sm">
                      <button
                        type="button"
                        disabled={row.progress <= 0}
                        onClick={() => onIncrement(row.id, row.progress - 1)}
                        aria-label="Decrease progress"
                        className="flex h-5 w-5 items-center justify-center rounded bg-surface-container-high font-bold text-on-surface hover:bg-surface-variant disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        −
                      </button>
                      <span className="font-bold text-on-surface">{formatChapter(row.progress)}</span>
                      <button
                        type="button"
                        onClick={() => onIncrement(row.id, row.progress + 1)}
                        aria-label="Increase progress"
                        className="flex h-5 w-5 items-center justify-center rounded bg-primary/20 font-bold text-on-primary-container hover:bg-primary hover:text-on-primary"
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
                  {row.status ? <StatusPill status={row.status} /> : <span className="font-mono text-label-sm text-outline">—</span>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
