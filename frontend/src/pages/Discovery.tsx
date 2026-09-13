import { useEffect, useState } from 'react'

import { api, ListStatusValue, Suggestion, SuggestionSource } from '../api'
import { DEFAULT_STATUS, STATUSES, downloadsByDefault } from '../listStatus'
import { useJobEvents } from '../useEvents'
import { Unmatched } from './Unmatched'

function reasonOf(suggestion: Suggestion): string {
  const { origin_title, origin_status, total_episodes } = suggestion.reason
  if (!origin_title) return 'Related to an anime on your list'
  const episodes = total_episodes ? ` (${total_episodes} episodes)` : ''
  const watched = origin_status === 'completed' ? `completed anime${episodes}` : `airing anime${episodes}`
  const chapters = suggestion.total_chapters
  const beyond = chapters ? ` — manga goes up to chapter ${chapters}` : ''
  return `from ${origin_title}, ${watched}${beyond}`
}

// The chips answer "where can I read this", so they are one per site, not one
// per candidate: a title with several MangaDex hits must not repeat the chip.
function uniqueSources(item: Suggestion): SuggestionSource[] {
  const bestBySite = new Map<string, SuggestionSource>()
  for (const source of item.sources) {
    const current = bestBySite.get(source.site)
    if (!current || source.score > current.score) bestBySite.set(source.site, source)
  }
  const preferredSite = item.best_source?.site
  return [...bestBySite.values()].sort((a, b) => {
    if (a.site === preferredSite) return -1
    if (b.site === preferredSite) return 1
    return b.score - a.score
  })
}

function whenOf(at?: string): string {
  if (!at) return ''
  const stamp = new Date(at)
  return Number.isNaN(stamp.getTime()) ? '' : ` (${stamp.toLocaleString()})`
}

/**
 * Both halves of "what should I read next" live here: the titles a relation
 * found on its own, and the anime that need a search by hand. One question
 * asked two ways, so one screen with two views rather than two nav entries.
 */
export function Discovery({ onChanged }: { onChanged: () => void }) {
  const [view, setView] = useState<'suggestions' | 'unmatched'>('suggestions')
  const [unmatchedTotal, setUnmatchedTotal] = useState<number | null>(null)
  const [items, setItems] = useState<Suggestion[]>([])
  const [writeFailures, setWriteFailures] = useState<Suggestion[]>([])
  const [choice, setChoice] = useState<Record<number, { status: ListStatusValue; download: boolean }>>({})
  const [busy, setBusy] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const load = () => {
    api.suggestions('new').then(setItems).catch((e) => setError(String(e)))
    // The card is gone by the time LIST_WRITE finishes, so a rejected status or a
    // stale token would otherwise never reach the user.
    api
      .suggestions('added')
      // A skipped target is an absence, not a failure: MangaDex without personal
      // credentials is the default setup, and it has nothing to say to the user.
      .then((added) =>
        setWriteFailures(added.filter((s) => s.write_results.some((r) => !r.ok && !r.skipped))),
      )
      .catch((e) => setError(String(e)))
  }

  useEffect(load, [])
  useJobEvents(load)

  // Counting the unmatched anime is a database read, not a provider search, so
  // the tab can carry its number without anything being searched on mount.
  useEffect(() => {
    api
      .unmatched({ limit: 1 })
      .then((page) => setUnmatchedTotal(page.total))
      .catch(() => undefined)
  }, [])

  const settingFor = (item: Suggestion) =>
    choice[item.id] ?? { status: DEFAULT_STATUS, download: downloadsByDefault(DEFAULT_STATUS) }

  const setStatus = (item: Suggestion, status: ListStatusValue) =>
    setChoice((current) => ({
      ...current,
      [item.id]: { status, download: downloadsByDefault(status) },
    }))

  const setDownload = (item: Suggestion, download: boolean) =>
    setChoice((current) => ({ ...current, [item.id]: { ...settingFor(item), download } }))

  const add = async (item: Suggestion) => {
    const { status, download } = settingFor(item)
    setBusy(item.id)
    try {
      const result = await api.addSuggestion(item.id, status, download)
      setItems((current) => current.filter((s) => s.id !== item.id))
      // The card goes away either way, so the only chance to say the mapping is
      // pending is here: nothing downloads until the source is confirmed.
      setNotice(
        result.needs_review
          ? `${item.title}: no source was reliable enough. The series is waiting in Review — confirm the source there${download ? ' and the download starts' : ''}.`
          : null,
      )
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
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <section>
      <header className="page-head">
        <h1>Discovery</h1>
        {view === 'suggestions' && (
          <button onClick={() => api.refreshDiscovery().then(load)}>Search now</button>
        )}
      </header>
      <div className="toolbar">
        <button
          className={view === 'suggestions' ? 'primary' : ''}
          onClick={() => setView('suggestions')}
        >
          Suggestions{items.length > 0 && ` (${items.length})`}
        </button>
        <button
          className={view === 'unmatched' ? 'primary' : ''}
          onClick={() => setView('unmatched')}
        >
          No match found{unmatchedTotal !== null && ` (${unmatchedTotal})`}
        </button>
      </div>
      {view === 'unmatched' ? (
        <Unmatched onChanged={onChanged} onTotal={setUnmatchedTotal} />
      ) : (
        <>
        {error && <p className="row-error">{error}</p>}
        {notice && <p className="notice">{notice}</p>}
        {writeFailures.length > 0 && (
          <div className="panel">
            <h2>Status not saved to every list</h2>
            {writeFailures.map((item) => (
              <p key={item.id} className="row-error">
                {item.title} —{' '}
                {item.write_results
                  .filter((result) => !result.ok && !result.skipped)
                  .map(
                    (result) =>
                      `${result.target}: ${result.error ?? 'failure with no details'}${whenOf(result.at)}`,
                  )
                  .join(' · ')}
              </p>
            ))}
          </div>
        )}
        {items.length === 0 && (
          <p className="empty">Nothing new. Everything on the anime list already has a manga match.</p>
        )}
        <div className="grid">
          {items.map((item) => (
            <article className="card" key={item.id}>
              {item.cover_url && <img src={item.cover_url} alt="" loading="lazy" />}
              <h2>{item.title}</h2>
              <p className="reason">{reasonOf(item)}</p>
              <p className="sources">
                {uniqueSources(item).map((source) => (
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
                Download now
              </label>
              <div className="actions">
                <button disabled={busy === item.id} onClick={() => add(item)}>
                  Add
                </button>
                <button className="ghost" disabled={busy === item.id} onClick={() => dismiss(item)}>
                  Dismiss
                </button>
              </div>
            </article>
          ))}
        </div>
        </>
      )}
    </section>
  )
}
