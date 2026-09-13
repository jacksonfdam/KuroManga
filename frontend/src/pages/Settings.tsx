import { useEffect, useState } from 'react'

import { api, type SettingsPayload } from '../api'

const FIELDS: Array<{ key: string; label: string; hint?: string }> = [
  { key: 'download_concurrency', label: 'Parallel downloads' },
  { key: 'per_source_concurrency', label: 'Parallel downloads per source site' },
  { key: 'cron_list_sync', label: 'List sync schedule (cron)', hint: 'worker restart required' },
  {
    key: 'cron_chapter_discover',
    label: 'Chapter discovery schedule (cron)',
    hint: 'worker restart required',
  },
  { key: 'auto_download_new', label: 'Search sources for new entries (true/false)' },
]

export function Settings() {
  const [data, setData] = useState<SettingsPayload | null>(null)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [status, setStatus] = useState<string | null>(null)

  const load = () => {
    api.settings().then((payload) => {
      setData(payload)
      setDraft(payload.values)
    })
  }

  useEffect(load, [])

  const connect = async (provider: string) => {
    try {
      const { url } = await api.authStart(provider)
      window.location.href = url
    } catch (error) {
      setStatus(String(error))
    }
  }

  if (!data) return <div className="empty">Loading…</div>

  return (
    <>
      <h1>Settings</h1>
      <p className="sub">Library at {data.library_path}</p>

      <h2>Lists</h2>
      <div className="panel">
        {Object.entries(data.providers).map(([provider, info]) => (
          <div
            key={provider}
            style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0' }}
          >
            <b style={{ width: 90 }}>{provider}</b>
            {info.connected ? (
              <span className="pill mapped">connected{info.account_name ? ` · ${info.account_name}` : ''}</span>
            ) : info.configured ? (
              <span className="pill needs_review">not connected</span>
            ) : (
              <span className="pill">client id missing in .env</span>
            )}
            <span style={{ flex: 1 }} />
            <button onClick={() => api.sync(provider).then(() => setStatus('sync queued'))}>
              Sync now
            </button>
            {info.connected ? (
              <button onClick={() => api.disconnect(provider).then(load)}>Disconnect</button>
            ) : (
              <button className="primary" disabled={!info.configured} onClick={() => connect(provider)}>
                Connect
              </button>
            )}
          </div>
        ))}
      </div>

      <h2>Pipeline</h2>
      <div className="panel">
        {FIELDS.map((field) => (
          <div key={field.key} className="field">
            <label>
              {field.label} {field.hint && <span className="kbd">{field.hint}</span>}
            </label>
            <input
              value={draft[field.key] ?? ''}
              onChange={(event) => setDraft({ ...draft, [field.key]: event.target.value })}
            />
          </div>
        ))}
        <button
          className="primary"
          onClick={() =>
            api.saveSettings(draft).then((payload) => {
              setData({ ...data, values: payload.values })
              setStatus('saved')
            })
          }
        >
          Save
        </button>
        {status && <span className="meta" style={{ marginLeft: 10 }}>{status}</span>}
      </div>
    </>
  )
}
