import { Icon, Toggle } from '../../ui'

// Left/right split taken from the Komga section in
// .redesign/ajustes_configura_es_do_homelab_integra_es/code.html. The mockup's
// container mount path, Komga instance URL, library id/series count and
// reindex button are dropped: KOMGA_URL and the library name are process env,
// not a setting, and nothing in the API queries Komga's own library metadata
// or triggers a rescan directly. Its three automation toggles (ComicInfo.xml
// generation, komga_scan-on-completion, progress_push as an on/off switch) are
// dropped too — those steps run unconditionally as part of the job chain, and
// there is no boolean settings key for any of them. Auto-download and the
// progress-push schedule are the two automation knobs this API actually has.
export function StorageFields({
  libraryPath,
  draft,
  onChange,
}: {
  libraryPath: string
  draft: Record<string, string>
  onChange: (key: string, value: string) => void
}) {
  return (
    // One quarter and three, not one third and two, and items-start rather
    // than the default stretch. The left card was sized for the mockup's
    // container mount path, Komga URL, library id, series count and reindex
    // button; all five were dropped for lack of a field, and the span kept
    // reserving a third of the row and 183px of height for them.
    <div className="grid grid-cols-1 items-start gap-space-md lg:grid-cols-4">
      <div className="flex flex-col gap-space-md rounded-xl bg-surface-container p-space-lg shadow-card lg:col-span-1">
        <div className="flex items-center gap-space-sm">
          <Icon name="folder" className="h-5 w-5 text-primary" />
          <h3 className="text-title-md font-semibold text-on-surface">Library Path</h3>
        </div>
        <div className="flex flex-col gap-space-xs">
          <span className="text-body-sm text-on-surface-variant">Host volume path</span>
          <div className="flex items-center justify-between gap-space-sm rounded-lg bg-surface-container-lowest p-space-sm">
            <code className="truncate font-mono text-label-sm text-secondary">{libraryPath}</code>
            <Icon name="lock" className="h-3 w-3 shrink-0 text-outline" />
          </div>
        </div>
      </div>
      <div className="flex flex-col gap-space-md rounded-xl bg-surface-container p-space-lg shadow-card lg:col-span-3">
        <h3 className="text-title-md font-semibold text-on-surface">Automation</h3>
        <div className="flex flex-col gap-space-xs rounded-lg bg-surface-container-low p-space-md">
          <Toggle
            checked={draft.auto_download_new === 'true'}
            onChange={(checked) => onChange('auto_download_new', checked ? 'true' : 'false')}
            label="Auto-download new entries"
          />
          <p className="text-body-sm text-on-surface-variant">
            When a list sync finds a new entry, queue a source search for it automatically.
          </p>
        </div>
        <div className="flex flex-col gap-space-xs rounded-lg bg-surface-container-low p-space-md">
          <span className="text-title-md text-on-surface">Progress push schedule</span>
          <p className="text-body-sm text-on-surface-variant">
            How often confirmed reading progress is pushed back to MyAnimeList and AniList (
            <code className="font-mono text-primary">cron_progress_push</code>).
          </p>
          <div className="mt-space-xs flex items-center gap-space-sm">
            <Icon name="sync" className="h-4 w-4 shrink-0 text-outline" />
            <input
              id="cron_progress_push"
              name="cron_progress_push"
              type="text"
              aria-label="Progress push schedule"
              value={draft.cron_progress_push ?? ''}
              onChange={(event) => onChange('cron_progress_push', event.target.value)}
              className="w-full rounded-lg bg-surface-container-lowest px-space-md py-space-sm font-mono text-label-md text-primary shadow-inner focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
        </div>
      </div>
    </div>
  )
}
