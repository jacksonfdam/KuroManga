import { useEffect, useState } from 'react'

import { api, ListStatusValue, Suggestion } from '../api'
import { useJobEvents } from '../useEvents'

const STATUSES: { value: ListStatusValue; label: string }[] = [
  { value: 'reading', label: 'Lendo' },
  { value: 'plan_to_read', label: 'Planejo ler' },
  { value: 'completed', label: 'Completo' },
  { value: 'on_hold', label: 'Em espera' },
  { value: 'dropped', label: 'Dropado' },
]

const DOWNLOADS_BY_DEFAULT: ListStatusValue[] = ['reading', 'plan_to_read']

function reasonOf(suggestion: Suggestion): string {
  const { origin_title, origin_status } = suggestion.reason
  if (!origin_title) return 'Relacionado a um anime da sua lista'
  const watched = origin_status === 'completed' ? 'anime completo' : 'anime em andamento'
  const chapters = suggestion.total_chapters
  const beyond = chapters ? ` — mangá vai até o capítulo ${chapters}` : ''
  return `de ${origin_title}, ${watched}${beyond}`
}

export function Discovery({ onChanged }: { onChanged: () => void }) {
  const [items, setItems] = useState<Suggestion[]>([])
  const [choice, setChoice] = useState<Record<number, { status: ListStatusValue; download: boolean }>>({})
  const [busy, setBusy] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    api.suggestions('new').then(setItems).catch((e) => setError(String(e)))
  }

  useEffect(load, [])
  useJobEvents(load)

  const settingFor = (item: Suggestion) =>
    choice[item.id] ?? { status: 'reading' as ListStatusValue, download: true }

  const setStatus = (item: Suggestion, status: ListStatusValue) =>
    setChoice((current) => ({
      ...current,
      [item.id]: { status, download: DOWNLOADS_BY_DEFAULT.includes(status) },
    }))

  const setDownload = (item: Suggestion, download: boolean) =>
    setChoice((current) => ({ ...current, [item.id]: { ...settingFor(item), download } }))

  const add = async (item: Suggestion) => {
    const { status, download } = settingFor(item)
    setBusy(item.id)
    try {
      await api.addSuggestion(item.id, status, download)
      setItems((current) => current.filter((s) => s.id !== item.id))
      onChanged()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(null)
    }
  }

  const dismiss = async (item: Suggestion) => {
    setBusy(item.id)
    try {
      await api.dismissSuggestion(item.id)
      setItems((current) => current.filter((s) => s.id !== item.id))
      onChanged()
    } finally {
      setBusy(null)
    }
  }

  return (
    <section>
      <header className="page-head">
        <h1>Discovery</h1>
        <button onClick={() => api.refreshDiscovery().then(load)}>Procurar agora</button>
      </header>
      {error && <p className="error">{error}</p>}
      {items.length === 0 && <p className="empty">Nada novo. A lista de anime já virou mangá.</p>}
      <div className="grid">
        {items.map((item) => (
          <article className="card" key={item.id}>
            {item.cover_url && <img src={item.cover_url} alt="" loading="lazy" />}
            <h2>{item.title}</h2>
            <p className="reason">{reasonOf(item)}</p>
            <p className="sources">
              {item.sources.map((source) => (
                <span
                  key={source.site}
                  className={source.site === item.best_source?.site ? 'chip chip-best' : 'chip'}
                >
                  {source.site}
                </span>
              ))}
            </p>
            <label>
              Status
              <select
                value={settingFor(item).status}
                onChange={(event) => setStatus(item, event.target.value as ListStatusValue)}
              >
                {STATUSES.map((status) => (
                  <option key={status.value} value={status.value}>
                    {status.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="toggle">
              <input
                type="checkbox"
                checked={settingFor(item).download}
                onChange={(event) => setDownload(item, event.target.checked)}
              />
              Baixar agora
            </label>
            <div className="actions">
              <button disabled={busy === item.id} onClick={() => add(item)}>
                Adicionar
              </button>
              <button className="ghost" disabled={busy === item.id} onClick={() => dismiss(item)}>
                Dispensar
              </button>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
