import { Link } from 'react-router-dom'

import { Button, Icon, buttonClass } from '../../ui'
import type { DashboardIntegrations } from '../../lib/api'

/**
 * "Pipeline operational" is a claim, not a caption.
 *
 * The mockup's line reads "5 de 5 brokers sincronizados" under a green dot,
 * which is true on the day everything is connected and a lie on every other
 * day. The same three fields answer all three cases, so the wording moves with
 * them rather than staying green over a red count.
 */
function pipeline(connected: number, total: number) {
  if (total > 0 && connected === total) {
    return { dot: 'bg-secondary', text: 'text-secondary', label: 'Pipeline operational' }
  }
  if (connected > 0) {
    return { dot: 'bg-warning', text: 'text-warning', label: 'Pipeline degraded' }
  }
  return { dot: 'bg-error', text: 'text-error', label: 'Pipeline offline' }
}

export function PipelineHeader({
  integrations,
  onForceScan,
}: {
  integrations: DashboardIntegrations
  onForceScan: () => void
}) {
  const { connected, total } = integrations
  const state = pipeline(connected, total)

  return (
    <section className="flex flex-col gap-space-md">
      <div className="flex items-center gap-space-sm">
        <span aria-hidden="true" className={`h-2 w-2 rounded-full ${state.dot}`} />
        <span className={`font-mono text-label-md ${state.text}`}>{state.label}</span>
        <span aria-hidden="true" className="text-outline-variant">
          ·
        </span>
        <span className="font-mono text-label-md text-outline">
          {connected} of {total} integrations connected
        </span>
      </div>

      <div className="flex flex-wrap items-end justify-between gap-space-md">
        <div className="max-w-2xl">
          <h1 className="text-headline-lg font-extrabold tracking-tight text-on-surface">
            KuroManga
          </h1>
          <p className="mt-1 text-body-md text-on-surface-variant">
            One view of the pipeline: what the index knows, what the acquisition queue is
            doing, and how it is orchestrating AniList, MyAnimeList and Komga.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-space-sm">
          <Button variant="surface" icon="sync" onClick={onForceScan}>
            Force scan
          </Button>
          {/* One link where there were two, to Review and to Discovery. They
              are one screen now, and it carries its own count in the nav a few
              pixels away - repeating it here would be the same number twice. */}
          <Link to="/discover" className={buttonClass({ variant: 'primary' })}>
            <Icon name="sparkle" />
            Open Discover
          </Link>
        </div>
      </div>
    </section>
  )
}
