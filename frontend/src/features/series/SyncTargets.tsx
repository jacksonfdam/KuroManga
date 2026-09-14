import { Card, StatusPill } from '../../ui'
import type { SeriesEntry } from '../../lib/api'
import { PROVIDER_LABEL, STATUS_ORDER, formatChapter, relativeTime } from '../../lib/format'

const KNOWN_STATUSES = new Set(STATUS_ORDER)

// Markup reference: "Sincronia Multi-Destino" in
// .redesign/detalhes_do_mang_gest_o_de_pipeline_sincronia_multi_destino/code.html.
// The reference marks every row "[OK]" and adds a Komga row and an
// "Auto-Push Ativo" badge — none of which the API reports (there is no
// per-provider health check, and Komga is not a list_entry). Each row here is
// exactly one `entries[]` item: the provider, its own id, its list status and
// the chapter it last wrote.
export function SyncTargets({ entries }: { entries: SeriesEntry[] }) {
  return (
    <Card as="section" elevated className="flex flex-col gap-space-sm">
      <h2 className="text-title-md text-on-surface">Sync targets</h2>
      {entries.length === 0 ? (
        <p className="text-body-sm text-on-surface-variant">Not synced to a reading list yet.</p>
      ) : (
        <div className="flex flex-col gap-space-xs">
          {entries.map((entry) => (
            <div
              key={entry.provider}
              className="flex items-center justify-between gap-space-sm rounded-lg bg-surface-container-low px-space-sm py-space-xs"
            >
              <div className="flex min-w-0 flex-col">
                <span className="text-body-sm font-semibold text-on-surface">
                  {PROVIDER_LABEL[entry.provider] ?? entry.provider}
                </span>
                <span className="truncate font-mono text-label-sm text-outline">#{entry.provider_media_id}</span>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                {entry.status && KNOWN_STATUSES.has(entry.status) && <StatusPill status={entry.status} />}
                <span className="font-mono text-label-sm text-outline">
                  Ch {formatChapter(entry.user_progress_chapter)}
                  {entry.updated_at && <> · {relativeTime(entry.updated_at)}</>}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}
