import { useCallback, useEffect, useState } from 'react'

import { api, type Integration } from '../../lib/api'
import { useAsyncData } from '../../lib/useAsyncData'
import { useNotice } from '../../lib/useNotice'

// Mirrors backend/app/settings_store.py's Defaults dataclass. "Restore defaults"
// only edits the draft, same as typing a new value by hand — nothing is written
// until Save runs, so a restore the user didn't mean to keep is still reversible.
const DEFAULT_VALUES: Record<string, string> = {
  cron_list_sync: '0 */6 * * *',
  cron_chapter_discover: '0 */2 * * *',
  cron_progress_push: '30 * * * *',
  cron_anime_list_sync: '0 */12 * * *',
  download_concurrency: '3',
  per_source_concurrency: '2',
  source_search_concurrency: '4',
  source_search_timeout: '20',
  download_batch_size: '20',
  auto_download_new: 'true',
  comick_url: '',
  comick_enabled: 'false',
}

export function useSettings() {
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [restartRequired, setRestartRequired] = useState(false)
  const [integrations, setIntegrations] = useState<Integration[]>([])
  const [saving, setSaving] = useState(false)
  const { notice, report, reportFailure, clear } = useNotice()

  const load = useCallback(() => api.settings(), [])
  const { data, error, reload, setData } = useAsyncData(load)

  const refreshIntegrations = useCallback(() => {
    // The source cards and the header strip both read this endpoint, so a
    // change here (a save, a connect, a disconnect) has to be re-fetched
    // through the same call rather than inferred from local/draft state, or
    // the two can end up disagreeing about whether a provider is connected.
    // A failure here leaves every card reading "not configured", which is a
    // different claim from "we could not ask" — so it is reported, not eaten.
    api.integrations().then(setIntegrations).catch(reportFailure)
  }, [reportFailure])

  useEffect(refreshIntegrations, [refreshIntegrations])

  // The draft is the saved values until the user edits them, so it follows
  // every load that actually landed.
  useEffect(() => {
    if (data) setDraft(data.values)
  }, [data])

  const dirty = data !== null && Object.keys(draft).some((key) => draft[key] !== data.values[key])

  const setField = useCallback(
    (key: string, value: string) => {
      setDraft((current) => ({ ...current, [key]: value }))
      // A stale "Settings saved" must not survive the next edit — the status
      // line otherwise contradicts the dirty dot next to it.
      clear()
    },
    [clear],
  )

  const restoreDefaults = useCallback(() => {
    setDraft((current) => ({ ...current, ...DEFAULT_VALUES }))
    clear()
  }, [clear])

  const save = useCallback(() => {
    setSaving(true)
    // Only the fields that actually changed. The API decides whether a worker
    // restart is needed from the keys it was sent, so posting the whole draft
    // claimed a cron change on every save, including saves that touched none.
    const changed = Object.fromEntries(
      Object.keys(draft)
        .filter((key) => draft[key] !== data?.values[key])
        .map((key) => [key, draft[key]]),
    )
    api
      .saveSettings(changed)
      .then((payload) => {
        setData((current) => (current ? { ...current, values: payload.values } : current))
        setDraft(payload.values)
        // The cron expressions are read once, when the worker starts its
        // scheduler. Reporting a plain "Settings saved" for a schedule that
        // will not run until the next restart is the API telling the truth
        // and the screen not passing it on.
        setRestartRequired(payload.restart_worker_required)
        report('Settings saved')
        // comick_url/comick_enabled may have just changed; the Comick card's
        // health state has to catch up to what was actually saved.
        refreshIntegrations()
      })
      .catch(reportFailure)
      .finally(() => setSaving(false))
  }, [data, draft, refreshIntegrations, report, reportFailure, setData])

  const connect = useCallback(
    async (provider: string) => {
      try {
        const { url } = await api.authStart(provider)
        window.location.href = url
      } catch (failure) {
        reportFailure(failure)
      }
    },
    [reportFailure],
  )

  const disconnect = useCallback(
    (provider: string) => {
      api
        .disconnect(provider)
        .then(() => {
          report(`${provider}: disconnected`)
          reload()
          refreshIntegrations()
        })
        .catch(reportFailure)
    },
    [refreshIntegrations, reload, report, reportFailure],
  )

  const sync = useCallback(
    (provider: string) => {
      api
        .sync(provider)
        .then(() => report(`${provider}: sync queued`))
        .catch(reportFailure)
    },
    [report, reportFailure],
  )

  const integration = useCallback(
    (name: string) => integrations.find((item) => item.name === name),
    [integrations],
  )

  return {
    data,
    error,
    reload,
    draft,
    dirty,
    restartRequired,
    saving,
    notice,
    setField,
    restoreDefaults,
    save,
    connect,
    disconnect,
    sync,
    integration,
  }
}
