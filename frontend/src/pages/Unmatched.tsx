import { useCallback, useEffect, useState } from 'react'

import {
  api,
  type ListStatusValue,
  type SearchCandidate,
  type SearchProviderError,
  type UnmatchedAnime,
  type UnmatchedSearch,
} from '../api'
import { DEFAULT_STATUS, STATUSES, downloadsByDefault } from '../listStatus'

// A row grows tall once its candidates are open, so a page is kept short enough
// that the pager under it stays reachable.
const PAGE_SIZE = 25

const PROVIDER_NAMES: Record<string, string> = { anilist: 'AniList', mal: 'MyAnimeList' }

const providerName = (provider: string) => PROVIDER_NAMES[provider] ?? provider

const fold = (title: string) => title.trim().toLowerCase()

/**
 * Which providers actually searched for something other than the title the
 * screen shows - MyAnimeList substitutes a name the anime is also known by,
 * or a trimmed prefix, when the AniList spelling is a query it will refuse.
 * Silent when nothing was substituted: a line that always fires is noise.
 */
function substitutedQueries(found: UnmatchedSearch): [string, string][] {
  return Object.entries(found.queries).filter(([, query]) => fold(query) !== fold(found.query))
}

/**
 * The four codes ask the user for four different things — authorise, wait,
 * retry, nothing — which is the whole reason the API sends a code instead of a
 * sentence. The last one is the one that must not read as a retry: the provider
 * refuses the query itself and would refuse it again.
 */
function errorMessage(failure: SearchProviderError): string {
  const who = providerName(failure.provider)
  switch (failure.code) {
    case 'not_connected':
      return `${who} is not connected. Authorise it in Settings, then search again.`
    case 'rate_limited':
      return `${who} is taking too many requests right now. Wait a moment and search again.`
    case 'query_unsupported':
      return `${who} cannot search for any title this anime goes by, so it was not asked. Searching again would answer the same.`
    default:
      return `${who} did not answer. Try the search again.`
  }
}

const FORMAT_LABELS: Record<string, string> = {
  MANGA: 'Manga',
  MANHWA: 'Manhwa',
  MANHUA: 'Manhua',
  OEL: 'OEL',
}

const PUBLISHING_LABELS: Record<string, string> = {
  FINISHED: 'Finished',
  RELEASING: 'Releasing',
  NOT_YET_RELEASED: 'Not yet released',
  HIATUS: 'On hiatus',
  CANCELLED: 'Cancelled',
}

interface KnownState {
  label: string
  tone: string
  note: string
  // True only for the state the add route answers with a 409, so the screen
  // never offers a button that cannot work.
  blocks: boolean
}

const KNOWN_STATES: Record<string, KnownState> = {
  added: {
    label: 'Already added',
    tone: 'pill known',
    note: 'You added this one already — it is in your library.',
    blocks: true,
  },
  on_list: {
    label: 'On your list',
    tone: 'pill known',
    note: 'Already on one of your lists. Adding it writes the status you pick over the one you have.',
    blocks: false,
  },
  dismissed: {
    label: 'Dismissed before',
    tone: 'pill',
    note: 'You turned this one down earlier.',
    blocks: false,
  },
  suggested: {
    label: 'Already suggested',
    tone: 'pill',
    note: 'This is waiting for you under Suggestions.',
    blocks: false,
  },
}

interface Notice {
  text: string
  tone: 'info' | 'warn'
  undo?: () => void
}

const titleOf = (anime: UnmatchedAnime) =>
  anime.title || anime.title_english || anime.title_romaji || `Anime ${anime.media_id}`

const candidateKey = (anime: UnmatchedAnime, candidate: SearchCandidate) =>
  `${anime.id}:${candidate.provider}:${candidate.media_id}`

const cover = (url: string | null) => (url ? { backgroundImage: `url(${url})` } : undefined)

/**
 * The anime no relation could turn into a manga. Nothing here searches on its
 * own: a provider is asked about one anime, at the moment the user asks.
 */
export function Unmatched({
  onChanged,
  onTotal,
}: {
  onChanged: () => void
  onTotal: (total: number) => void
}) {
  const [items, setItems] = useState<UnmatchedAnime[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [typed, setTyped] = useState('')
  const [filter, setFilter] = useState('')
  const [showHidden, setShowHidden] = useState(false)
  const [results, setResults] = useState<Record<number, UnmatchedSearch>>({})
  const [searching, setSearching] = useState<number | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [choice, setChoice] = useState<
    Record<string, { status: ListStatusValue; download: boolean }>
  >({})
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<Notice | null>(null)

  const load = useCallback(async () => {
    try {
      const page = await api.unmatched({
        hidden: showHidden,
        q: filter,
        limit: PAGE_SIZE,
        offset,
      })
      setItems(page.items)
      setTotal(page.total)
      // The hidden listing is its own set rather than the rest of this one, and
      // a filtered count is a slice of neither, so neither belongs on the tab.
      if (!showHidden && !filter) onTotal(page.total)
      if (page.total > 0 && offset >= page.total) setOffset(Math.max(0, page.total - PAGE_SIZE))
    } catch (err) {
      setError(String(err))
    }
  }, [showHidden, filter, offset, onTotal])

  useEffect(() => {
    load()
  }, [load])

  // The server holds the whole list, so the box asks it rather than sifting the
  // twenty-five rows on screen — and the keystrokes are collected first, or one
  // typed word is a request per letter.
  useEffect(() => {
    const settle = setTimeout(() => {
      setFilter(typed.trim())
      setOffset(0)
    }, 250)
    return () => clearTimeout(settle)
  }, [typed])

  const swapView = (hidden: boolean) => {
    setShowHidden(hidden)
    setOffset(0)
    setNotice(null)
  }

  const search = async (anime: UnmatchedAnime) => {
    setSearching(anime.id)
    setError(null)
    try {
      const found = await api.searchUnmatched(anime.id)
      setResults((current) => ({ ...current, [anime.id]: found }))
    } catch (err) {
      setError(String(err))
    } finally {
      setSearching(null)
    }
  }

  const settingFor = (key: string) =>
    choice[key] ?? { status: DEFAULT_STATUS, download: downloadsByDefault(DEFAULT_STATUS) }

  const setStatus = (key: string, status: ListStatusValue) =>
    setChoice((current) => ({ ...current, [key]: { status, download: downloadsByDefault(status) } }))

  const setDownload = (key: string, download: boolean) =>
    setChoice((current) => ({ ...current, [key]: { ...settingFor(key), download } }))

  const add = async (anime: UnmatchedAnime, candidate: SearchCandidate) => {
    const key = candidateKey(anime, candidate)
    const { status, download } = settingFor(key)
    setBusy(key)
    setError(null)
    try {
      const result = await api.addUnmatched(anime.id, candidate, status, download)
      // The row leaves the list on the next load, so this is the only moment
      // left to say that nothing is downloading yet.
      setNotice(
        result.needs_review
          ? {
              tone: 'warn',
              text: `${candidate.title} added. No source was reliable enough to map it, so the series is waiting in Review — confirm the source there${download ? ' and the download starts' : ''}.`,
            }
          : {
              tone: 'info',
              text: `${candidate.title} added.${download ? ' Its chapters are queued under Downloads.' : ' Nothing is downloading — start it from Library when you want it.'}`,
            },
      )
      setResults((current) => {
        const next = { ...current }
        delete next[anime.id]
        return next
      })
      onChanged()
      await load()
    } catch (err) {
      setError(String(err))
    } finally {
      setBusy(null)
    }
  }

  const setHidden = async (anime: UnmatchedAnime, hidden: boolean) => {
    setBusy(`hide:${anime.id}`)
    setError(null)
    try {
      await (hidden ? api.hideUnmatched(anime.id) : api.unhideUnmatched(anime.id))
      setNotice({
        tone: 'info',
        text: hidden
          ? `${titleOf(anime)} hidden. It is under Hidden if you want it back.`
          : `${titleOf(anime)} is back on the list.`,
        // Hiding is one click beside hundreds of rows, so the mis-click is
        // answered here instead of sending the user through the other tab.
        // Unhiding needs no undo: the anime is back where it can be hidden again.
        undo: hidden ? () => setHidden(anime, false) : undefined,
      })
      await load()
    } catch (err) {
      setError(String(err))
    } finally {
      setBusy(null)
    }
  }

  const renderCandidate = (anime: UnmatchedAnime, candidate: SearchCandidate) => {
    const key = candidateKey(anime, candidate)
    const known = candidate.known_state ? KNOWN_STATES[candidate.known_state] : undefined
    const setting = settingFor(key)
    const blocked = known?.blocks ?? false
    return (
      <article className="card candidate" key={key}>
        <span className="thumb" style={cover(candidate.cover_url)} />
        <div className="candidate-body">
          <span className="title">{candidate.title}</span>
          <div className="meta">
            <span
              className={candidate.format ? 'pill' : 'pill unsure'}
              title={
                candidate.format
                  ? undefined
                  : 'Neither provider said what this is. It may not be a manga — check before you add it.'
              }
            >
              {candidate.format
                ? (FORMAT_LABELS[candidate.format] ?? candidate.format)
                : 'Type not stated'}
            </span>
            {candidate.year && <span>{candidate.year}</span>}
            <span>
              {candidate.total_chapters
                ? `${candidate.total_chapters} chapters`
                : 'chapter count unknown'}
            </span>
            <span>{Math.round(candidate.score * 100)}% match</span>
          </div>
          <div className="sources">
            {candidate.providers.map((provider) => (
              <span key={provider} className="chip">
                {providerName(provider)}
              </span>
            ))}
            {candidate.publishing_status && (
              <span className="chip">
                {PUBLISHING_LABELS[candidate.publishing_status] ?? candidate.publishing_status}
              </span>
            )}
            {known && <span className={known.tone}>{known.label}</span>}
          </div>
          {known && <p className="reason">{known.note}</p>}
          <label>
            Status
            <select
              value={setting.status}
              disabled={blocked}
              onChange={(event) => setStatus(key, event.target.value as ListStatusValue)}
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
              checked={setting.download}
              disabled={blocked}
              onChange={(event) => setDownload(key, event.target.checked)}
            />
            Download now
          </label>
          <div className="actions">
            <button
              className="primary"
              disabled={blocked || busy === key}
              onClick={() => add(anime, candidate)}
            >
              {blocked ? 'Already added' : busy === key ? 'Adding…' : 'Add'}
            </button>
          </div>
        </div>
      </article>
    )
  }

  const renderResult = (anime: UnmatchedAnime, found: UnmatchedSearch) => (
    <>
      {/* A provider that failed is reported beside the other's results, never
          instead of them. */}
      {found.errors.map((failure) => (
        <p key={failure.provider} className="row-error" title={failure.detail}>
          {errorMessage(failure)}
        </p>
      ))}
      {/* Quiet whenever every provider searched for the title already shown
          above - only worth a line when one of them answered a different
          question than the user was told was asked. */}
      {substitutedQueries(found).map(([provider, query]) => (
        <p key={provider} className="meta">
          {providerName(provider)} searched for “{query}” instead.
        </p>
      ))}
      {found.candidates.length === 0 ? (
        <p className="empty">
          {found.errors.length > 0
            ? `Nothing found for “${found.query}” by the provider that answered.`
            : `No manga found for “${found.query}”. Both providers answered and neither had a match.`}
        </p>
      ) : (
        <>
          <p className="reason" style={{ margin: '10px 0 0' }}>
            {found.candidates.length} result{found.candidates.length === 1 ? '' : 's'} for “
            {found.query}”
          </p>
          <div className="candidates roomy">
            {found.candidates.map((candidate) => renderCandidate(anime, candidate))}
          </div>
        </>
      )}
    </>
  )

  const renderAnime = (anime: UnmatchedAnime) => {
    const found = results[anime.id]
    const name = titleOf(anime)
    return (
      <article className="panel" key={anime.id}>
        <div className="unmatched-row">
          <span className="thumb" style={cover(anime.cover_url)} />
          <div className="grow">
            <span className="title">{name}</span>
            {anime.title_romaji && anime.title_romaji !== name && (
              <span className="meta">{anime.title_romaji}</span>
            )}
            <div className="meta">
              <span className="pill">{anime.status.replace('_', ' ')}</span>
              <span>
                {anime.progress_episode} / {anime.total_episodes ?? '?'} episodes watched
              </span>
              {anime.providers.map((provider) => (
                <span key={provider} className="pill">
                  {providerName(provider)}
                </span>
              ))}
            </div>
          </div>
          <div className="actions">
            {!showHidden && (
              <button
                className="primary"
                disabled={searching !== null || busy !== null}
                onClick={() => search(anime)}
                title="Asks AniList and MyAnimeList about this one title"
              >
                {searching === anime.id ? 'Searching…' : found ? 'Search again' : 'Search by title'}
              </button>
            )}
            <button
              className="ghost"
              disabled={busy !== null}
              onClick={() => setHidden(anime, !showHidden)}
            >
              {showHidden ? 'Unhide' : 'Hide'}
            </button>
          </div>
        </div>
        {searching === anime.id && (
          <p className="searching">
            Asking AniList and MyAnimeList for “{anime.title_romaji || name}” — two providers, so
            give it a moment.
          </p>
        )}
        {found && renderResult(anime, found)}
      </article>
    )
  }

  return (
    <>
      <div className="toolbar">
        <button className={showHidden ? '' : 'primary'} onClick={() => swapView(false)}>
          Without a match
        </button>
        <button className={showHidden ? 'primary' : ''} onClick={() => swapView(true)}>
          Hidden
        </button>
        <input
          placeholder="Filter by title"
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
        />
      </div>

      <p className="sub">
        {filter
          ? `${total} ${showHidden ? 'hidden anime' : 'anime'} matching “${filter}”. The whole list is filtered, not the page you are on.`
          : showHidden
            ? 'The anime you hid, listed on their own. Unhide one to put it back where it can be searched.'
            : `${total} anime on your list that no relation could turn into a manga. Nothing is searched until you ask for it.`}
      </p>

      {error && <p className="row-error">{error}</p>}
      {notice && (
        <p className={notice.tone === 'warn' ? 'notice' : 'notice info'}>
          {notice.text}
          {notice.undo && (
            <button className="undo" onClick={notice.undo}>
              Undo
            </button>
          )}
        </p>
      )}

      {items.length === 0 ? (
        <div className="empty">
          {filter
            ? `Nothing matches “${filter}”. Every spelling an anime is known by is read, so try part of another one.`
            : showHidden
              ? 'Nothing hidden. Anything you hide on the other tab waits here.'
              : 'Nothing left. Every anime on your list has a manga match or is hidden.'}
        </div>
      ) : (
        items.map(renderAnime)
      )}

      {items.length > 0 && (
        <div className="page-nav">
          <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
            Previous
          </button>
          <button disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>
            Next
          </button>
          <span>
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
          </span>
        </div>
      )}
    </>
  )
}
