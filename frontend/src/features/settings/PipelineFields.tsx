import type { ReactNode } from 'react'

import { Icon } from '../../ui'

// The six fields in .redesign/ajustes_configura_es_do_homelab_integra_es/code.html's
// pipeline section: three semaphore/batch numbers, three cron schedules. The
// mockup's "BullMQ / PgPool: 12 conexões" section badge is dropped — this queue
// is Postgres via app/queue/repo.py, not BullMQ, and nothing reports a live
// connection count.
function hoursHint(cron: string): string | null {
  const match = /^0 \*\/(\d+) \* \* \*$/.exec(cron.trim())
  if (!match) return null
  const hours = Number(match[1])
  return `Every ${hours} hour${hours === 1 ? '' : 's'}`
}

function FieldCard({ label, hint, description, children }: { label: string; hint?: string | null; description: ReactNode; children: ReactNode }) {
  return (
    <div className="flex flex-col justify-between gap-space-sm rounded-xl bg-surface-container p-space-lg shadow-sm">
      <div>
        <div className="mb-1 flex items-center justify-between gap-space-sm">
          <span className="text-title-md font-semibold text-on-surface">{label}</span>
          {hint && (
            <span className="rounded bg-surface-container-high px-2 py-0.5 font-mono text-label-sm text-secondary">
              {hint}
            </span>
          )}
        </div>
        <p className="text-body-sm text-on-surface-variant">{description}</p>
      </div>
      {children}
    </div>
  )
}

function NumberInput({
  settingKey,
  label,
  value,
  unit,
  min,
  max,
  step,
  onChange,
}: {
  settingKey: string
  label: string
  value: string
  unit: string
  min: number
  max: number
  step?: number
  onChange: (value: string) => void
}) {
  return (
    <div className="mt-space-sm flex items-center gap-space-sm">
      <input
        id={settingKey}
        name={settingKey}
        type="number"
        aria-label={label}
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-lg bg-surface-container-lowest px-space-md py-space-sm font-mono text-label-md text-on-surface shadow-inner focus:outline-none focus:ring-2 focus:ring-primary"
      />
      <span className="shrink-0 font-mono text-label-sm text-on-surface-variant">{unit}</span>
    </div>
  )
}

function CronInput({
  settingKey,
  label,
  value,
  onChange,
}: {
  settingKey: string
  label: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <div className="mt-space-sm flex items-center gap-space-sm">
      <Icon name="sync" className="h-4 w-4 shrink-0 text-outline" />
      <input
        id={settingKey}
        name={settingKey}
        type="text"
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-lg bg-surface-container-lowest px-space-md py-space-sm font-mono text-label-md text-primary shadow-inner focus:outline-none focus:ring-2 focus:ring-primary"
      />
    </div>
  )
}

export function PipelineFields({
  draft,
  onChange,
}: {
  draft: Record<string, string>
  onChange: (key: string, value: string) => void
}) {
  return (
    <div className="grid grid-cols-1 gap-space-md md:grid-cols-2 lg:grid-cols-3">
      <FieldCard label="Worker Concurrency" description="Parallel downloads the engine runs globally.">
        <NumberInput
          settingKey="download_concurrency"
          label="Worker Concurrency"
          value={draft.download_concurrency ?? ''}
          unit="workers"
          min={1}
          max={16}
          onChange={(value) => onChange('download_concurrency', value)}
        />
      </FieldCard>
      <FieldCard label="Host Semaphore" description="Parallel downloads per source domain, to stay clear of an IP ban or HTTP 429.">
        <NumberInput
          settingKey="per_source_concurrency"
          label="Host Semaphore"
          value={draft.per_source_concurrency ?? ''}
          unit="req/host"
          min={1}
          max={5}
          onChange={(value) => onChange('per_source_concurrency', value)}
        />
      </FieldCard>
      <FieldCard label="Batch Size" description="Chapters requested per batch (keeps MangaDex from answering with a 400).">
        <NumberInput
          settingKey="download_batch_size"
          label="Batch Size"
          value={draft.download_batch_size ?? ''}
          unit="chapters"
          min={5}
          max={50}
          step={5}
          onChange={(value) => onChange('download_batch_size', value)}
        />
      </FieldCard>
      <FieldCard
        label="List Sync"
        hint={hoursHint(draft.cron_list_sync ?? '')}
        description={
          <>
            Bidirectional MyAnimeList / AniList update (<code className="font-mono text-primary">cron_list_sync</code>).
          </>
        }
      >
        <CronInput settingKey="cron_list_sync" label="List Sync" value={draft.cron_list_sync ?? ''} onChange={(value) => onChange('cron_list_sync', value)} />
      </FieldCard>
      <FieldCard
        label="Chapter Discovery"
        hint={hoursHint(draft.cron_chapter_discover ?? '')}
        description={
          <>
            Scan confirmed sources for newly released chapters (
            <code className="font-mono text-primary">cron_chapter_discover</code>).
          </>
        }
      >
        <CronInput
          settingKey="cron_chapter_discover"
          label="Chapter Discovery"
          value={draft.cron_chapter_discover ?? ''}
          onChange={(value) => onChange('cron_chapter_discover', value)}
        />
      </FieldCard>
      <FieldCard
        label="Anime Sync (suggestions)"
        hint={hoursHint(draft.cron_anime_list_sync ?? '')}
        description={
          <>
            Cross-reference completed anime to suggest manga (
            <code className="font-mono text-primary">cron_anime_list_sync</code>).
          </>
        }
      >
        <CronInput settingKey="cron_anime_list_sync" label="Anime Sync (suggestions)" value={draft.cron_anime_list_sync ?? ''} onChange={(value) => onChange('cron_anime_list_sync', value)} />
      </FieldCard>
    </div>
  )
}
