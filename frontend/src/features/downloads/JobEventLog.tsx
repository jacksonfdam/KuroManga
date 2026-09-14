import type { JobEvent } from '../../lib/api'

// No mockup covers this screen. Styled as a plain terminal-like log block —
// mono type on the lowest surface tier — rather than inventing a new
// component pattern for a list of timestamped lines.
export function JobEventLog({ events }: { events: JobEvent[] }) {
  if (events.length === 0) {
    return (
      <p className="rounded-lg bg-surface-container-lowest px-3 py-2 font-mono text-label-sm text-outline">
        No events yet.
      </p>
    )
  }

  return (
    <div className="flex max-h-64 flex-col gap-0.5 overflow-y-auto rounded-lg bg-surface-container-lowest p-3">
      {events.map((event, index) => (
        <div
          key={index}
          className={`flex gap-2 font-mono text-label-sm ${
            event.level === 'error' ? 'text-error' : 'text-on-surface-variant'
          }`}
        >
          <span className="shrink-0 text-outline">{event.ts.slice(11, 19)}</span>
          {event.pct !== null && <span className="shrink-0 text-tertiary">{Math.round(event.pct)}%</span>}
          <span className="truncate">{event.message}</span>
        </div>
      ))}
    </div>
  )
}
