import { Icon } from '../../ui'
import type { Series } from '../../lib/api'
import { formatChapter, relativeTime } from '../../lib/format'
import { totalChapters } from './useLibrary'
import { QuickIncrement } from './QuickIncrement'

// Markup reference: the "Continuar de Onde Parou" hero row in
// .redesign/biblioteca_principal_sincronizada_com_komga_provedores/code.html.
// Only series with an updated_at get here, so relativeTime never sees null.
export function ContinueReading({
  series,
  onIncrement,
}: {
  series: Series[]
  onIncrement: (id: number, next: number) => Promise<void>
}) {
  if (series.length === 0) return null

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center gap-2.5">
        <Icon name="sparkle" className="h-5 w-5 text-primary" />
        <h2 className="text-headline-sm font-bold tracking-tight text-on-surface">Continue reading</h2>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {series.map((row) => {
          const total = totalChapters(row)
          return (
            <div
              key={row.id}
              className="flex items-center gap-4 rounded-xl bg-surface-container-low p-4 shadow-card"
            >
              <div className="h-28 w-20 shrink-0 overflow-hidden rounded-lg bg-surface-container-highest shadow-sm">
                {row.cover_url && <img src={row.cover_url} alt="" className="h-full w-full object-cover" />}
              </div>
              <div className="flex h-full min-w-0 flex-1 flex-col justify-between py-0.5">
                <div>
                  <div className="mb-1 flex items-center justify-between gap-1 font-mono text-label-sm text-outline">
                    <span className="truncate">{row.title}</span>
                    <span className="shrink-0">{relativeTime(row.updated_at as string)}</span>
                  </div>
                  <p className="mt-0.5 font-mono text-label-md text-on-surface-variant">
                    Ch {formatChapter(row.progress)}
                    {total !== null && <span className="text-outline"> / {total}</span>}
                  </p>
                </div>
                <div className="mt-3 flex items-center gap-2">
                  <QuickIncrement progress={row.progress} onIncrement={(next) => onIncrement(row.id, next)} />
                  <span className="font-mono text-label-sm text-outline">+1 Ch</span>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
