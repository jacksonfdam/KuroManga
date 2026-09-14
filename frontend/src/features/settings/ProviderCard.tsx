import { relativeTime } from '../../lib/format'
import { Button, Card } from '../../ui'

// Markup taken from the MyAnimeList / AniList cards in
// .redesign/ajustes_configura_es_do_homelab_integra_es/code.html. The mockup's
// token-validity progress bar and "Forçar Renovação" / "Testar Conexão"
// buttons are dropped: nothing in the API reports an issued-at timestamp or
// exposes a renew/test-connection action, and a bar with an invented percentage
// would be worse than no bar.
const DOT: Record<string, string> = {
  ok: 'bg-secondary',
  unauthenticated: 'bg-warning',
  unreachable: 'bg-error',
}

const STATE_LABEL: Record<string, string> = {
  ok: 'Connected',
  unauthenticated: 'Not connected',
  unreachable: 'Unreachable',
}

export function ProviderCard({
  tile,
  title,
  subtitle,
  info,
  state,
  onConnect,
  onDisconnect,
  onSync,
}: {
  tile: string
  title: string
  subtitle: string
  info: { connected: boolean; configured: boolean; account_name?: string; expires_at?: string | null }
  state?: string
  onConnect: () => void
  onDisconnect: () => void
  onSync: () => void
}) {
  const dot = DOT[state ?? ''] ?? 'bg-outline'
  const label = STATE_LABEL[state ?? ''] ?? 'Unknown'

  return (
    <Card elevated className="flex flex-col justify-between gap-space-lg">
      <div className="flex flex-col gap-space-md">
        <div className="flex items-center gap-space-sm">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-surface-container-highest font-mono text-headline-md font-black text-primary">
            {tile}
          </div>
          <div className="flex flex-col">
            <span className="text-title-md text-on-surface">{title}</span>
            <span className="text-body-sm text-on-surface-variant">{subtitle}</span>
          </div>
        </div>
        <div className="flex flex-col gap-space-sm rounded-lg bg-surface-container-low p-space-md">
          <div className="flex items-center justify-between text-body-sm">
            <span className="flex items-center gap-1.5 text-on-surface-variant">
              <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
              {label}
            </span>
            {info.account_name && (
              <span className="font-mono text-label-sm text-on-surface">{info.account_name}</span>
            )}
          </div>
          {!info.configured && (
            <span className="font-mono text-label-sm text-warning">Client ID missing in .env</span>
          )}
          {info.expires_at && (
            <div className="flex items-center justify-between text-body-sm">
              <span className="text-on-surface-variant">Token expires</span>
              <span className="font-mono text-label-sm font-semibold text-secondary">
                {relativeTime(info.expires_at)}
              </span>
            </div>
          )}
        </div>
      </div>
      <div className="flex items-center justify-end gap-space-sm">
        <Button variant="surface" size="sm" icon="sync" disabled={!info.configured} onClick={onSync}>
          Sync now
        </Button>
        {info.connected ? (
          <Button variant="danger" size="sm" icon="link" onClick={onDisconnect}>
            Disconnect
          </Button>
        ) : (
          <Button variant="primary" size="sm" icon="link" disabled={!info.configured} onClick={onConnect}>
            Connect
          </Button>
        )}
      </div>
    </Card>
  )
}
