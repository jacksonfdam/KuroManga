import type { ReactNode } from 'react'

import { Button, ErrorState, Icon, NoticeBar, Skeleton, Toggle, type IconName } from '../../ui'
import { ProviderCard } from './ProviderCard'
import { PipelineFields } from './PipelineFields'
import { SourcesPanel } from './SourcesPanel'
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
  // `sources` answers in two shapes: MangaDex carries an account, comick has
  // none and only reports whether it answers. Narrowing rather than reaching
  // for `.username` keeps a comick-shaped answer from reading as a MangaDex
  // that is merely signed out.
  const mangadexSource = data.sources.mangadex
  const mangadexUser =
    mangadexSource && 'username' in mangadexSource ? mangadexSource.username : null
  const komga = integration('komga')

  // MangaBaka has no /api/health/integrations entry — that endpoint reads
  // provider_token rows and a token provider never writes one — so its half of
  // the count comes from the settings payload, which is where its state lives.
  const mangabaka = data.providers.mangabaka
  const activeConnections =
    [mal, anilist].filter((item) => item?.state === 'ok').length +
    (mangabaka?.configured ? 1 : 0)
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
          title="List Providers & Authentication"
          subtitle="Primary reading-tracking and score-sync sources"
          meta={
            <span className="rounded bg-surface-container-low px-space-sm py-1 font-mono text-label-sm text-on-surface-variant">
              {activeConnections} active connection{activeConnections === 1 ? '' : 's'}
            </span>
          }
        />
        <div className="grid grid-cols-1 gap-space-md lg:grid-cols-2">
          <ProviderCard
            provider="mal"
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
            provider="anilist"
            tile="AL"
            title="AniList"
            subtitle="OAuth2 authorization code"
            info={data.providers.anilist}
            state={anilist?.state}
            onConnect={() => connect('anilist')}
            onDisconnect={() => disconnect('anilist')}
            onSync={() => sync('anilist')}
          />
          <ProviderCard
            provider="mangabaka"
            tile="MB"
            title="MangaBaka"
            subtitle="Static API token (X-API-Key)"
            info={data.providers.mangabaka}
            onSync={() => sync('mangabaka')}
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
        {/* items-start: the MangaDex card is one paragraph and the Comick card
            beside it carries a URL field and a toggle, so stretching them to a
            common height left the reference's API-key and rate-limit rows — both
            dropped, neither in this API — reserved as empty space. */}
        <div className="grid grid-cols-1 items-start gap-space-md lg:grid-cols-2">
          <SourceCard
            icon="download"
            title="MangaDex API"
            subtitle="https://api.mangadex.org"
            tone={mangadex?.state === 'ok' ? 'ok' : 'neutral'}
            statusLabel={
              mangadex?.state === 'ok'
                ? `Authenticated${mangadexUser ? ` as ${mangadexUser}` : ''}`
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
          <SourceCard
            icon="lock"
            title="MangaFire"
            subtitle="Cloudflare, cleared by FlareSolverr"
            tone={draft.mangafire_waf_pass ? 'ok' : 'neutral'}
            statusLabel={draft.mangafire_waf_pass ? 'Cookie set' : 'Cookie not set'}
          >
            {/* The site gates its API behind an image puzzle its own app solves
                in a browser. Nothing here solves it: a person does, in their
                browser, and pastes what that produced. */}
            <div className="flex flex-col gap-space-xs">
              <label htmlFor="mangafire-waf" className="text-body-sm text-on-surface-variant">
                waf_pass cookie
              </label>
              <input
                id="mangafire-waf"
                name="mangafire_waf_pass"
                type="text"
                spellCheck={false}
                autoComplete="off"
                placeholder="paste the cookie value"
                value={draft.mangafire_waf_pass ?? ''}
                onChange={(event) => setField('mangafire_waf_pass', event.target.value)}
                className="w-full rounded-lg bg-surface-container-lowest px-space-md py-space-sm font-mono text-label-md text-tertiary shadow-inner focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <p className="text-body-sm text-on-surface-variant">
                Usually not needed. The site sits behind Cloudflare, which FlareSolverr clears on
                its own — start it with
                <code className="mx-1 font-mono text-primary">--profile flaresolverr</code>
                and leave this empty. Fill it in only if the site raises its own challenge: clear
                that in your browser, then copy the
                <code className="mx-1 font-mono text-primary">waf_pass</code>
                cookie here.
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
          icon="search"
          title="Sources"
          subtitle="Which scan sites are searched when a series needs a match"
        />
        <SourcesPanel />
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

      <div className="sticky bottom-nav-clearance z-40 mt-space-md w-full xl:bottom-space-lg">
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
