import { useCallback, useEffect, useState } from 'react'

import { api, type SearchCandidate, type UnmatchedAnime, type UnmatchedSearch } from '../../lib/api'
import { DEFAULT_STATUS, downloadsByDefault, type ListStatus } from '../../lib/format'
import { useAsyncData } from '../../lib/useAsyncData'
import { useNotice } from '../../lib/useNotice'
import { candidateKey, titleOf } from './labels'

// A row grows tall once its candidates are open, so a page is kept short enough
// that the pager under it stays reachable.
export const PAGE_SIZE = 25

export interface Choice {
  status: ListStatus
  download: boolean
}

export function useUnmatched(onChanged: () => void) {
  const [offset, setOffset] = useState(0)
  const [typed, setTyped] = useState('')
  const [filter, setFilter] = useState('')
  const [showHidden, setShowHidden] = useState(false)
  const [results, setResults] = useState<Record<number, UnmatchedSearch>>({})
  const [searching, setSearching] = useState<number | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [choice, setChoice] = useState<Record<string, Choice>>({})
  const [undo, setUndo] = useState<(() => void) | null>(null)
  const { notice, report, fail, reportFailure, clear } = useNotice()

  const load = useCallback(
    () => api.unmatched({ hidden: showHidden, q: filter, limit: PAGE_SIZE, offset }),
    [showHidden, filter, offset],
  )

  const { data, error, reload } = useAsyncData(load)
  const total = data?.total ?? 0

  // A page that was emptied by a hide (or by the filter tightening) leaves the
  // offset past the end, and the list would come back blank with rows still on
  // the previous page.
  useEffect(() => {
    if (total > 0 && offset >= total) setOffset(Math.max(0, total - PAGE_SIZE))
  }, [offset, total])

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

  const swapView = useCallback(
    (hidden: boolean) => {
      setShowHidden(hidden)
      setOffset(0)
      clear()
      setUndo(null)
    },
    [clear],
  )

  const search = useCallback(
    async (anime: UnmatchedAnime) => {
      setSearching(anime.id)
      clear()
      setUndo(null)
      try {
        const found = await api.searchUnmatched(anime.id)
        setResults((current) => ({ ...current, [anime.id]: found }))
      } catch (failure) {
        reportFailure(failure)
      } finally {
        setSearching(null)
      }
    },
    [clear, reportFailure],
  )

  const settingFor = useCallback(
    (key: string): Choice =>
      choice[key] ?? { status: DEFAULT_STATUS, download: downloadsByDefault(DEFAULT_STATUS) },
    [choice],
  )

  const setStatus = useCallback(
    (key: string, status: ListStatus) =>
      setChoice((current) => ({ ...current, [key]: { status, download: downloadsByDefault(status) } })),
    [],
  )

  const setDownload = useCallback(
    (key: string, download: boolean) =>
      setChoice((current) => ({
        ...current,
        [key]: { status: current[key]?.status ?? DEFAULT_STATUS, download },
      })),
    [],
  )

  const add = useCallback(
    async (anime: UnmatchedAnime, candidate: SearchCandidate) => {
      const key = candidateKey(anime.id, candidate.provider, candidate.media_id)
      const { status, download } = settingFor(key)
      setBusy(key)
      clear()
      setUndo(null)
      try {
        const result = await api.addUnmatched(anime.id, candidate, status, download)
        // The row leaves the list on the next load, so this is the only moment
        // left to say that nothing is downloading yet.
        if (result.needs_review) {
          fail(
            `${candidate.title} added. No source was reliable enough to map it, so the series is waiting in Review — confirm the source there${
              download ? ' and the download starts' : ''
            }.`,
          )
        } else {
          report(
            `${candidate.title} added.${
              download
                ? ' Its chapters are queued under Downloads.'
                : ' Nothing is downloading — start it from Library when you want it.'
            }`,
          )
        }
        setResults((current) => {
          const next = { ...current }
          delete next[anime.id]
          return next
        })
        onChanged()
        reload()
      } catch (failure) {
        reportFailure(failure)
      } finally {
        setBusy(null)
      }
    },
    [clear, fail, onChanged, reload, report, reportFailure, settingFor],
  )

  const setHidden = useCallback(
    async (anime: UnmatchedAnime, hidden: boolean) => {
      setBusy(`hide:${anime.id}`)
      clear()
      setUndo(null)
      try {
        await (hidden ? api.hideUnmatched(anime.id) : api.unhideUnmatched(anime.id))
        report(
          hidden
            ? `${titleOf(anime)} hidden. It is under Hidden if you want it back.`
            : `${titleOf(anime)} is back on the list.`,
        )
        // Hiding is one click beside hundreds of rows, so the mis-click is
        // answered here instead of sending the user through the other tab.
        // Unhiding needs no undo: the anime is back where it can be hidden again.
        setUndo(hidden ? () => () => setHidden(anime, false) : null)
        reload()
      } catch (failure) {
        reportFailure(failure)
      } finally {
        setBusy(null)
      }
    },
    [clear, reload, report, reportFailure],
  )

  return {
    items: data?.items ?? [],
    total,
    loaded: data !== null,
    error,
    reload,
    notice,
    undo,
    offset,
    setOffset,
    typed,
    setTyped,
    filter,
    showHidden,
    swapView,
    results,
    searching,
    busy,
    search,
    settingFor,
    setStatus,
    setDownload,
    add,
    setHidden,
  }
}
