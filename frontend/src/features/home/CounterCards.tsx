import { Card, Icon, type IconName } from '../../ui'
import type {
  ActiveReading,
  DiscoveryCounts,
  DownloadCounts,
  MappingCounts,
} from '../../lib/api'
import { PROVIDER_LABEL } from '../../lib/format'

const TONE: Record<string, string> = {
  primary: 'bg-primary/[0.12] text-primary',
  secondary: 'bg-secondary/[0.12] text-secondary',
  tertiary: 'bg-tertiary/[0.12] text-tertiary',
  warning: 'bg-warning/[0.12] text-warning',
}

function Counter({
  value,
  label,
  icon,
  tone,
  detail,
}: {
  value: number
  label: string
  icon: IconName
  tone: keyof typeof TONE
  /** One sentence saying what the number above is made of. Never a figure the
      payload does not carry — a counter with an invented sub-line is worse
      than one with a plain sub-line. */
  detail: string
}) {
  return (
    <Card elevated>
      <div className="flex items-start justify-between gap-space-sm">
        <div className="min-w-0">
          <p className="text-display-sm text-on-surface">{value}</p>
          <h2 className="mt-1 text-title-md text-on-surface">{label}</h2>
        </div>
        <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${TONE[tone]}`}>
          <Icon name={icon} className="h-5 w-5" />
        </span>
      </div>
      <p className="mt-space-sm font-mono text-label-sm text-outline">{detail}</p>
    </Card>
  )
}

function sourceList(sources: string[]): string {
  return sources.map((source) => PROVIDER_LABEL[source] ?? source).join(', ')
}

export function CounterCards({
  activeReading,
  downloads,
  mappings,
  discovery,
}: {
  activeReading: ActiveReading
  downloads: DownloadCounts
  mappings: MappingCounts
  discovery: DiscoveryCounts
}) {
  return (
    <div className="grid grid-cols-1 gap-space-md sm:grid-cols-2 xl:grid-cols-4">
      <Counter
        value={activeReading.series}
        label="Active reading"
        icon="book"
        tone="secondary"
        detail={
          activeReading.with_unread > 0
            ? `${activeReading.with_unread} with unread chapters`
            : 'Nothing unread on the shelf'
        }
      />
      <Counter
        value={downloads.in_flight}
        label="Download queue"
        icon="download"
        tone="tertiary"
        detail={
          downloads.sources.length > 0
            ? `Pulling from ${sourceList(downloads.sources)}`
            : downloads.queued > 0
              ? `${downloads.queued} waiting to start`
              : 'Nothing downloading'
        }
      />
      <Counter
        value={mappings.pending}
        label="Pending mappings"
        icon="link"
        tone="warning"
        detail={
          mappings.pending > 0
            ? 'Blocking Komga automation'
            : 'Every series has a source'
        }
      />
      <Counter
        value={discovery.new}
        label="Anime discovery"
        icon="sparkle"
        tone="primary"
        detail={
          discovery.new > 0
            ? [
                discovery.providers.length > 0 ? `From ${sourceList(discovery.providers)}` : null,
                discovery.new_today > 0 ? `${discovery.new_today} today` : null,
              ]
                .filter(Boolean)
                .join(' · ') || 'Waiting for an answer'
            : 'Nothing new to look at'
        }
      />
    </div>
  )
}
