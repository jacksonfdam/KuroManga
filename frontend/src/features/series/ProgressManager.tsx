import { useState } from 'react'

import { Card, Icon, NoticeBar, ProgressBar, SegmentedControl } from '../../ui'
import type { ListStatus } from '../../lib/format'
import { messageOf, type SeriesDetail } from '../../lib/api'
import { formatChapter, relativeTime } from '../../lib/format'
import { useIncrementFlash } from '../../ui/useIncrementFlash'

// The three the mockup's own control offers. The full vocabulary has five;
// plan-to-read and dropped are set on the provider, not from a reading screen.
const STATUS_OPTIONS: { value: ListStatus; label: string }[] = [
  { value: 'reading', label: 'Reading' },
  { value: 'on_hold', label: 'Paused' },
  { value: 'completed', label: 'Completed' },
]

/** A date as the user's locale writes it, or nothing when no date was given. */
function onDay(iso: string | null): string | null {
  if (!iso) return null
  const parsed = new Date(iso)
  return Number.isNaN(parsed.getTime()) ? iso : parsed.toLocaleDateString('en-GB')
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-space-sm">
      <span className="font-mono text-label-sm text-outline">{label}</span>
      <span className="font-mono text-label-md text-on-surface">{value}</span>
    </div>
  )
}

export function ProgressManager({
  detail,
  total,
  minutesPerChapter,
  queued,
  refusal,
  onProgress,
  onStatus,
}: {
  detail: SeriesDetail
  total: number | null
  /** `reading_minutes_per_chapter` from settings. The remaining-time figure is
   * derived from it and is labelled an estimate, because it is one. */
  minutesPerChapter: number | null
  /** The chapter the queue took, while no worker has written it yet. */
  queued: number | null
  /** Why the last chapter write was refused, whether on the click or later. */
  refusal: string | null
  onProgress: (next: number) => Promise<void>
  onStatus: (status: ListStatus) => Promise<void>
}) {
  const { series, metadata } = detail
  const { busy, trigger } = useIncrementFlash(onProgress)
  const [statusError, setStatusError] = useState<string | null>(null)
  const remaining = total != null ? Math.max(total - series.progress, 0) : null
  const estimate =
    remaining != null && minutesPerChapter != null ? remaining * minutesPerChapter : null

  const changeStatus = (status: ListStatus) => {
    setStatusError(null)
    onStatus(status).catch((failure: unknown) => setStatusError(messageOf(failure)))
  }

  return (
    <Card as="section" elevated className="flex flex-col gap-space-lg">
      <div className="flex flex-wrap items-center justify-between gap-space-md">
        <h2 className="text-headline-sm text-on-surface">Progress</h2>
        {/* Hidden entirely with no status at all — a control with nothing to
            select is worse than no control. plan_to_read and dropped are
            real values of the same vocabulary, set on the provider rather
            than from this screen, and correctly show no selection here: both
            are outside the three options this control offers. */}
        {series.status && (
          <SegmentedControl options={STATUS_OPTIONS} value={series.status} onChange={changeStatus} />
        )}
      </div>
      {statusError && <NoticeBar tone="error" text={statusError} />}
      {refusal && <NoticeBar tone="error" text={refusal} />}

      <div className="grid grid-cols-1 gap-space-lg md:grid-cols-2">
        <div className="flex flex-col gap-space-sm">
          <span className="font-mono text-label-sm uppercase tracking-wide text-outline">
            Chapters read
          </span>
          <div className="flex items-center gap-space-sm">
            <button
              type="button"
              disabled={busy || series.progress <= 0}
              onClick={() => void trigger(series.progress - 1)}
              aria-label="Step back one chapter"
              className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface-container-high text-on-surface transition-colors hover:bg-surface-bright disabled:cursor-not-allowed disabled:text-outline"
            >
              <Icon name="chevron" className="h-4 w-4 rotate-90" />
            </button>
            <span className="min-w-16 text-center text-headline-lg text-on-surface">
              {formatChapter(series.progress)}
            </span>
            <button
              type="button"
              disabled={busy}
              onClick={() => void trigger(series.progress + 1)}
              aria-label="Mark next chapter read"
              className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-on-primary transition-colors hover:bg-primary-container disabled:cursor-not-allowed"
            >
              <Icon name="add" className="h-4 w-4" />
            </button>
            {total != null && (
              <span className="font-mono text-label-md text-outline">/ {total}</span>
            )}
          </div>
          {total != null && (
            <ProgressBar value={series.progress} max={total} tone="secondary" />
          )}
          {/* The number above is one the queue took, not one the lists hold.
              Said plainly, because this screen is where a user checks what the
              providers were actually told. */}
          {queued != null && (
            <p className="flex items-center gap-space-xs font-mono text-label-sm text-tertiary">
              <Icon name="sync" className="h-3 w-3" />
              Chapter {formatChapter(queued)} queued — waiting to reach your lists
            </p>
          )}
          {remaining != null && (
            <p className="font-mono text-label-sm text-outline">
              {remaining} chapters left
              {/* Labelled an estimate because it is derived from a setting,
                  not measured. A number presented as measured when it was
                  assumed is worse than no number. */}
              {estimate != null && <> · about {Math.round(estimate / 60)}h estimated</>}
            </p>
          )}
        </div>

        <div className="flex flex-col gap-space-xs">
          {metadata.volumes_total != null && (
            <Row
              label="Volumes"
              // volumes_read is nullable independently of the total: a provider
              // can report how many volumes exist without reporting how many
              // were read. Showing "0 of 18" there would assert a count
              // nobody gave.
              value={
                metadata.volumes_read != null
                  ? `${metadata.volumes_read} of ${metadata.volumes_total}`
                  : `${metadata.volumes_total} in total`
              }
            />
          )}
          {onDay(metadata.started_at) && <Row label="Started" value={onDay(metadata.started_at)!} />}
          {onDay(metadata.completed_at) && (
            <Row label="Finished" value={onDay(metadata.completed_at)!} />
          )}
          {metadata.list_updated_at && (
            <Row label="Last updated" value={relativeTime(metadata.list_updated_at)} />
          )}
          {metadata.reread_count != null && (
            <Row label="Rereads" value={`${metadata.reread_count}`} />
          )}
        </div>
      </div>
    </Card>
  )
}
