import type { Source } from '../../lib/api'
import { Badge, Toggle } from '../../ui'

/**
 * One catalogue row. Presentational: the toggle reports the intent and the
 * hook decides what happens.
 */
export function SourceRow({
  source,
  busy,
  onToggle,
}: {
  source: Source
  busy: boolean
  onToggle: () => void
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-space-sm border-b border-outline-variant py-space-sm last:border-b-0">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-space-xs">
          <span className="text-body-md text-on-surface">{source.name}</span>
          {/* The content warning is a badge, not grounds for hiding the row:
              two of the sites this library depends on are declared mixed
              upstream, and a screen that hides the site the user came to find
              reads as the port having failed. */}
          {source.nsfw && <Badge tone="warning">18+</Badge>}
        </div>
        <span className="block truncate font-mono text-label-sm text-on-surface-variant">
          {source.base_url} · {source.template} · {source.lang}
        </span>
        {source.reason && (
          <span className="block text-label-sm text-on-surface-variant">{source.reason}</span>
        )}
      </div>
      <Toggle
        checked={source.enabled}
        // A site with a reason cannot run at all, so its toggle says so by
        // being inert rather than by accepting a click that changes nothing
        // the search will honour.
        disabled={busy || source.reason !== null}
        onChange={onToggle}
        label={source.enabled ? 'Searched' : 'Not searched'}
      />
    </div>
  )
}
