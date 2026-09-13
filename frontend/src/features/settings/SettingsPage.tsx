import type { ReactNode } from 'react'

import { Button, ErrorState, Icon, NoticeBar, Skeleton, Toggle, type IconName } from '../../ui'
import { ProviderCard } from './ProviderCard'
import { PipelineFields } from './PipelineFields'
import { SourceCard } from './SourceCard'
import { StorageFields } from './StorageFields'
import { useSettings } from './useSettings'

// Layout follows .redesign/ajustes_configura_es_do_homelab_integra_es/code.html
// section by section. The title banner's "Daemon Activo (PID 4092)" live-process
// line and the "Cluster Memory" tile are dropped outright: nothing in this API
// reports the worker process's own liveness or memory use, and a number invented
// to fill that space would be worse than an honest gap.
function SectionHeader({
  icon,
  title,
  subtitle,
  meta,
}: {
  icon: IconName
  title: string
  subtitle: string
  meta?: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-space-sm">
      <div className="flex items-center gap-space-sm">
        <div className="flex h-7 w-7 items-center justify-center rounded bg-primary/[0.12] text-primary">
          <Icon name={icon} className="h-4 w-4" />
        </div>
        <div>
          <h2 className="text-headline-sm font-semibold text-on-surface">{title}</h2>
          <p className="text-body-sm text-on-surface-variant">{subtitle}</p>
        </div>
      </div>
      {meta}
    </div>
  )
}

export function SettingsPage() {
  const { data, error, reload, draft, dirty, restartRequired, saving, notice, setField, restoreDefaults, save, connect, disconnect, sync, integration } =
    useSettings()

  // Without this the screen sat on "Loading…" forever: the fetch had no catch
  // at all, so a failed request left the only other branch unreachable.
  if (!data && error) {
    return <ErrorState title="Couldn't load the settings" detail={error} onRetry={reload} />
  }

  if (!data) {
    return (
      <div className="flex flex-col gap-space-lg">
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  const mal = integration('mal')
  const anilist = integration('anilist')
  const mangadex = integration('mangadex')
  const comick = integration('comick')
  const komga = integration('komga')

  const activeConnections = [mal, anilist].filter((item) => item?.state === 'ok').length
  const operationalSources = [mangadex, comick].filter((item) => item?.state === 'ok').length

  const komgaLabel =
    komga?.state === 'ok' ? 'Komga reachable' : komga?.state === 'unreachable' ? 'Komga unreachable' : 'Komga needs credentials'

  return (
    <div className="flex flex-col gap-space-xl pb-24">
      {error && <NoticeBar tone="error" text={`Couldn't refresh the settings: ${error}`} onRetry={reload} />}
      <div className="rounded-xl bg-surface-container p-space-lg shadow-xl">
        <div className="flex flex-col gap-space-xs">
          <span className="w-fit rounded-full bg-surface-container-high px-space-sm py-0.5 font-mono text-label-sm uppercase tracking-wider text-primary">
            Homelab core settings
          </span>
          <h1 className="text-headline-lg font-bold tracking-tight text-on-surface">
            System & Homelab Integrations Settings
          </h1>
          <p className="text-body-md text-on-surface-variant">
            Manage OAuth credentials, download pipeline parameters, the self-hosted Comick API, and Komga automation.
          </p>
        </div>
      </div>

      <section className="flex flex-col gap-space-md">
        <SectionHeader
          icon="link"
          title="List Providers & OAuth2 Authentication"
          subtitle="Primary reading-tracking and score-sync sources"
          meta={
            <span className="rounded bg-surface-container-low px-space-sm py-1 font-mono text-label-sm text-on-surface-variant">
              {activeConnections} active connection{activeConnections === 1 ? '' : 's'}
            </span>
          }
        />
        <div className="grid grid-cols-1 gap-space-md lg:grid-cols-2">
          <ProviderCard
            tile="MAL"
            title="MyAnimeList"
            subtitle="OAuth2 PKCE (plain method)"
            info={data.providers.mal}
            state={mal?.state}
            onConnect={() => connect('mal')}
            onDisconnect={() => disconnect('mal')}
            onSync={() => sync('mal')}
          />
          <ProviderCard
            tile="AL"
            title="AniList"
            subtitle="OAuth2 authorization code"
            info={data.providers.anilist}
            state={anilist?.state}
            onConnect={() => connect('anilist')}
            onDisconnect={() => disconnect('anilist')}
            onSync={() => sync('anilist')}
          />
        </div>
      </section>

      <section className="flex flex-col gap-space-md">
        <SectionHeader
          icon="download"
          title="Download Sources & Search Engines"
          subtitle="Scraping connectors, official REST endpoints and self-hosted scrapers"
          meta={
            <span className="font-mono text-label-sm font-semibold text-secondary">
              {operationalSources} source{operationalSources === 1 ? '' : 's'} operational
            </span>
          }
        />
        <div className="grid grid-cols-1 gap-space-md lg:grid-cols-2">
          <SourceCard
            icon="download"
            title="MangaDex API"
            subtitle="https://api.mangadex.org"
            tone={mangadex?.state === 'ok' ? 'ok' : 'neutral'}
            statusLabel={
              mangadex?.state === 'ok'
                ? `Authenticated${data.sources.mangadex.username ? ` as ${data.sources.mangadex.username}` : ''}`
                : 'Anonymous mode'
            }
          >
            <p className="text-body-sm text-on-surface-variant">
              Anonymous access is the normal mode. MangaDex caches anonymous responses but not authenticated ones, so
              signing in makes searches slower, not faster. Set the four MANGADEX_ variables in .env only if your
              account needs to see restricted titles.
            </p>
          </SourceCard>
          <SourceCard
            icon="server"
            title="Comick"
            subtitle="Self-hosted source API"
            tone={comick?.state === 'ok' ? 'ok' : 'neutral'}
            statusLabel={comick?.state === 'ok' ? 'URL configured' : 'URL not set'}
          >
            <div className="flex flex-col gap-space-xs">
              <label htmlFor="comick-url" className="text-body-sm text-on-surface-variant">
                Instance URL
              </label>
              <input
                id="comick-url"
                name="comick_url"
                type="text"
                placeholder="http://comick:3000"
                value={draft.comick_url ?? ''}
                onChange={(event) => setField('comick_url', event.target.value)}
                className="w-full rounded-lg bg-surface-container-lowest px-space-md py-space-sm font-mono text-label-md text-tertiary shadow-inner focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <div className="flex flex-col gap-space-xs rounded-lg bg-surface-container-low p-space-sm">
              <Toggle
                checked={draft.comick_enabled === 'true'}
                onChange={(checked) => setField('comick_enabled', checked ? 'true' : 'false')}
                label="Enable Comick as a source"
              />
              <p className="text-body-sm text-on-surface-variant">
                Include this instance when searching for and downloading chapters.
              </p>
            </div>
          </SourceCard>
        </div>
      </section>

      <section className="flex flex-col gap-space-md">
        <SectionHeader
          icon="settings"
          title="Download Pipeline & Queue Tuning"
          subtitle="Tune async semaphores, batch sizes and automation cron expressions"
        />
        {restartRequired && (
          <NoticeBar
            tone="info"
            text="Saved. The worker reads these schedules when it starts, so restart it for the new cron to take effect."
          />
        )}
        <PipelineFields draft={draft} onChange={setField} />
      </section>

      <section className="flex flex-col gap-space-md">
        <SectionHeader
          icon="folder"
          title="Komga Server & Storage"
          subtitle="CBZ library configuration and reverse reading-progress sync"
          meta={
            <span className="flex items-center gap-space-xs font-mono text-label-sm text-on-surface-variant">
              <span className={`h-2 w-2 rounded-full ${komga?.state === 'ok' ? 'bg-secondary' : 'bg-warning'}`} />
              {komgaLabel}
            </span>
          }
        />
        <StorageFields libraryPath={data.library_path} draft={draft} onChange={setField} />
      </section>

      <div className="sticky bottom-6 z-40 mt-space-md w-full">
        <div className="flex flex-col items-center justify-between gap-space-md rounded-xl bg-surface-container-lowest/90 p-space-md shadow-2xl backdrop-blur-xl sm:flex-row">
          <div className="flex items-center gap-space-sm">
            <span
              className={`h-3 w-3 rounded-full ${
                notice?.tone === 'error' ? 'bg-error' : dirty ? 'bg-warning' : 'bg-secondary'
              }`}
            />
            <span className="flex items-center gap-1 text-body-sm text-on-surface-variant">
              Configuration status:
              <strong
                className={`font-mono text-label-sm font-semibold ${
                  notice?.tone === 'error' ? 'text-error' : 'text-on-surface'
                }`}
              >
                {notice?.text ?? (dirty ? 'Unsaved changes' : 'No pending changes')}
              </strong>
            </span>
          </div>
          <div className="flex w-full items-center justify-end gap-space-sm sm:w-auto">
            <Button variant="surface" onClick={restoreDefaults}>
              Restore defaults
            </Button>
            <Button variant="primary" icon="save" disabled={!dirty || saving} onClick={save}>
              {saving ? 'Saving…' : 'Save changes'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
