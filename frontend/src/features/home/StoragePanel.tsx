import { Card, Icon, ProgressBar } from '../../ui'
import type { StorageUsage } from '../../lib/api'
import { formatBytes } from '../../lib/format'

/**
 * How much room the library has left.
 *
 * Three things the mockup shows here are not rendered, because /api/dashboard
 * does not serve them and could not without measuring something nothing
 * measures: a ZFS pool health verdict (statvfs reports capacity, not health),
 * the split by content type (that means stat-ing every file on every request),
 * and a throughput figure (the downloader's output carries no byte counts).
 *
 * A volume that is not mounted arrives with no byte fields at all rather than
 * zeroed ones, so it cannot draw as an empty pool.
 */
function tone(pct: number): 'primary' | 'warning' | 'error' {
  if (pct >= 90) return 'error'
  if (pct >= 75) return 'warning'
  return 'primary'
}

export function StoragePanel({ storage }: { storage: StorageUsage }) {
  return (
    <Card elevated>
      <div className="flex items-center gap-space-sm">
        <Icon name="folder" className="h-5 w-5 text-outline" />
        <h2 className="text-title-md text-on-surface">Storage</h2>
      </div>
      <p className="mt-space-xs truncate font-mono text-label-sm text-outline" title={storage.path}>
        {storage.path}
      </p>

      {!storage.available ? (
        <p className="mt-space-sm rounded-lg bg-warning/[0.12] px-space-sm py-space-xs text-body-sm text-warning">
          The library path could not be read, so there is nothing to measure: {storage.detail}
        </p>
      ) : (
        <>
          <div className="mt-space-md flex items-baseline justify-between gap-space-sm">
            <span className="text-display-sm text-on-surface">{storage.used_pct}%</span>
            <span className="font-mono text-label-md text-on-surface-variant">
              {formatBytes(storage.used_bytes)} of {formatBytes(storage.total_bytes)}
            </span>
          </div>
          <div className="mt-space-sm">
            <ProgressBar value={storage.used_pct} max={100} tone={tone(storage.used_pct)} />
          </div>
          <p className="mt-space-sm font-mono text-label-sm text-outline">
            {formatBytes(storage.free_bytes)} free on the volume holding the library
          </p>
        </>
      )}
    </Card>
  )
}
