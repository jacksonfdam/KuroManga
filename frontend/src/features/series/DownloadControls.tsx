import { useState } from 'react'

import { Button, Card, Toggle } from '../../ui'

// Reference shows an auto-computed "Batch Size 20: Caps 149-160" preview and
// a Komga rescan button; neither is a real number or endpoint this API
// exposes, so the range is a plain form instead of a precomputed silhouette.
export function DownloadControls({
  autoDownload,
  onToggleAutoDownload,
  onDownload,
  onQueued,
}: {
  autoDownload: boolean
  onToggleAutoDownload: (enabled: boolean) => Promise<void>
  onDownload: (from?: number, to?: number) => Promise<{ queued: number }>
  onQueued: () => void
}) {
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [status, setStatus] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    setBusy(true)
    setStatus(null)
    try {
      const result = await onDownload(from ? Number(from) : undefined, to ? Number(to) : undefined)
      setStatus(
        result.queued > 0
          ? `Queued ${result.queued} chapter${result.queued === 1 ? '' : 's'}.`
          : 'Nothing to queue in that range.',
      )
      onQueued()
    } catch (error) {
      setStatus(String(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card as="section" elevated className="flex flex-col gap-space-sm">
      <h2 className="text-title-md text-on-surface">Downloads</h2>
      <Toggle
        checked={autoDownload}
        onChange={(checked) => {
          onToggleAutoDownload(checked).catch(() => undefined)
        }}
        label="Auto-download new chapters"
      />
      <div className="flex flex-col gap-space-xs border-t border-surface-container-highest/40 pt-space-sm">
        <span className="font-mono text-label-sm text-on-surface-variant">Download a range</span>
        <div className="flex items-center gap-space-xs">
          <input
            name="download-from-chapter"
            aria-label="From chapter"
            placeholder="From"
            inputMode="decimal"
            value={from}
            onChange={(event) => setFrom(event.target.value)}
            className="w-full rounded-lg bg-surface-container-lowest px-3 py-2 text-body-sm text-on-surface placeholder:text-outline focus:outline-none focus:ring-1 focus:ring-primary"
          />
          <input
            name="download-to-chapter"
            aria-label="To chapter"
            placeholder="To"
            inputMode="decimal"
            value={to}
            onChange={(event) => setTo(event.target.value)}
            className="w-full rounded-lg bg-surface-container-lowest px-3 py-2 text-body-sm text-on-surface placeholder:text-outline focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        <Button variant="primary" size="sm" icon="download" disabled={busy} onClick={submit} className="w-fit">
          Queue download
        </Button>
        {status && <p className="font-mono text-label-sm text-outline">{status}</p>}
      </div>
    </Card>
  )
}
