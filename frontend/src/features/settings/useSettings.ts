import { useCallback, useEffect, useState } from 'react'

import { api, type Integration, type SettingsPayload } from '../../lib/api'

// Mirrors backend/app/settings_store.py's Defaults dataclass. "Restore defaults"
// only edits the draft, same as typing a new value by hand — nothing is written
// until Save runs, so a restore the user didn't mean to keep is still reversible.
const DEFAULT_VALUES: Record<string, string> = {
  cron_list_sync: '0 */6 * * *',
  cron_chapter_discover: '0 */2 * * *',
  cron_progress_push: '30 * * * *',
  cron_anime_sync: '0 */12 * * *',
  download_concurrency: '3',
  per_source_concurrency: '2',
  download_batch_size: '20',
  auto_download_new: 'true',
  comick_url: '',
  comick_enabled: 'false',
}

// A save failure must not read like a save success — the sticky bar renders
// this tone as an error, not the neutral/success styling "notice" used to get
// regardless of which one it was.
export interface Notice {
  text: string
  tone: 'info' | 'error'
}

export function useSettings() {
  const [data, setData] = useState<SettingsPayload | null>(null)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [integrations, setIntegrations] = useState<Integration[]>([])
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState<Notice | null>(null)

  const refreshIntegrations = useCallback(() => {
    // The source cards and the header strip both read this endpoint, so a
    // change here (a save, a connect, a disconnect) has to be re-fetched
    // through the same call rather than inferred from local/draft state, or
    // the two can end up disagreeing about whether a provider is connected.
    api.integrations().then(setIntegrations).catch(() => undefined)
  }, [])

  const load = useCallback(() => {
    api.settings().then((payload) => {
      setData(payload)
      setDraft(payload.values)
    })
    refreshIntegrations()
  }, [refreshIntegrations])

  useEffect(load, [load])

  const dirty = data !== null && Object.keys(draft).some((key) => draft[key] !== data.values[key])

  const setField = useCallback((key: string, value: string) => {
    setDraft((current) => ({ ...current, [key]: value }))
    // A stale "Settings saved" must not survive the next edit — the status
    // line otherwise contradicts the dirty dot next to it.
    setNotice(null)
  }, [])

  const restoreDefaults = useCallback(() => {
    setDraft((current) => ({ ...current, ...DEFAULT_VALUES }))
    setNotice(null)
  }, [])

  const save = useCallback(() => {
    setSaving(true)
    api
      .saveSettings(draft)
      .then((payload) => {
        setData((current) => (current ? { ...current, values: payload.values } : current))
        setDraft(payload.values)
        setNotice({ text: 'Settings saved', tone: 'info' })
        // comick_url/comick_enabled may have just changed; the Comick card's
        // health state has to catch up to what was actually saved.
        refreshIntegrations()
      })
      .catch((error) => setNotice({ text: String(error), tone: 'error' }))
      .finally(() => setSaving(false))
  }, [draft, refreshIntegrations])

  const connect = useCallback(async (provider: string) => {
    try {
      const { url } = await api.authStart(provider)
      window.location.href = url
    } catch (error) {
      setNotice({ text: String(error), tone: 'error' })
    }
  }, [])

  const disconnect = useCallback(
    (provider: string) => {
      api.disconnect(provider).then(load)
    },
    [load],
  )

  const sync = useCallback((provider: string) => {
    api
      .sync(provider)
      .then(() => setNotice({ text: `${provider}: sync queued`, tone: 'info' }))
      .catch((error) => setNotice({ text: String(error), tone: 'error' }))
  }, [])

  const integration = useCallback(
    (name: string) => integrations.find((item) => item.name === name),
    [integrations],
  )

  return {
    data,
    draft,
    dirty,
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
