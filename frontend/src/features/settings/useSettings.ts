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

export function useSettings() {
  const [data, setData] = useState<SettingsPayload | null>(null)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [integrations, setIntegrations] = useState<Integration[]>([])
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const load = useCallback(() => {
    api.settings().then((payload) => {
      setData(payload)
      setDraft(payload.values)
    })
    // Provider state comes from this same endpoint the header strip reads, so
    // the two can never disagree about whether a provider is authenticated.
    api.integrations().then(setIntegrations).catch(() => undefined)
  }, [])

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
        setNotice('Settings saved')
      })
      .catch((error) => setNotice(String(error)))
      .finally(() => setSaving(false))
  }, [draft])

  const connect = useCallback(async (provider: string) => {
    try {
      const { url } = await api.authStart(provider)
      window.location.href = url
    } catch (error) {
      setNotice(String(error))
    }
  }, [])

  const disconnect = useCallback(
    (provider: string) => {
      api.disconnect(provider).then(load)
    },
    [load],
  )

  const sync = useCallback((provider: string) => {
    api.sync(provider).then(() => setNotice(`${provider}: sync queued`))
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
