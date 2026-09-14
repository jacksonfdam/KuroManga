import { useCallback, useState } from 'react'

import { api, type Suggestion } from '../../lib/api'
import { DEFAULT_STATUS, downloadsByDefault, type ListStatus } from '../../lib/format'
import { useAsyncData } from '../../lib/useAsyncData'
import { useJobEvents } from '../../lib/useEvents'
import { useNotice } from '../../lib/useNotice'
import { useSuggestionActions } from '../../lib/useSuggestionActions'

export interface Choice {
  status: ListStatus
  download: boolean
}

interface Feed {
  items: Suggestion[]
  /** Every suggestion waiting, which is not items.length: the route pages at
      100 and the screen must not report its page as the total. */
  total: number
  /** Approved suggestions whose status never reached one of the lists. */
  writeFailures: Suggestion[]
}

/**
 * Both halves load as one unit. Split across two states, a failure between them
 * left the screen showing suggestions with no way to tell that the second
 * request had failed at all.
 */
export function useDiscovery(onChanged: () => void) {
  const [choice, setChoice] = useState<Record<number, Choice>>({})
  const notice = useNotice()
  const { report, reportFailure, clear } = notice

  const load = useCallback(async (): Promise<Feed> => {
    const [items, added, counts] = await Promise.all([
      api.suggestions('new'),
      api.suggestions('added', { writeFailed: true }),
      api.suggestionCounts(),
    ])
    return {
      items,
      total: counts.new ?? items.length,
      // The card is gone by the time LIST_WRITE finishes, so a rejected status
      // or a stale token would otherwise never reach the user.
      //
      // Asked of the database rather than filtered here: the list is ranked and
      // capped at a hundred, so once a hundred suggestions had been added, a
      // failure on an unpopular title fell off the page and the user never
      // heard about it. A skipped target is still an absence rather than a
      // failure — MangaDex without personal credentials is the default setup
      // and has nothing to say here — and the API applies that same rule.
      writeFailures: added,
    }
  }, [])

  const { data, error, reload } = useAsyncData(load)
  useJobEvents(reload)

  // Both the shell's badges and this list are stale the moment a suggestion is
  // answered, so an approval refreshes the two of them together.
  const changed = useCallback(() => {
    onChanged()
    reload()
  }, [onChanged, reload])

  const { busy, approve, dismiss } = useSuggestionActions(notice, changed)

  const settingFor = useCallback(
    (item: Suggestion): Choice =>
      choice[item.id] ?? {
        status: DEFAULT_STATUS,
        download: downloadsByDefault(DEFAULT_STATUS),
      },
    [choice],
  )

  const setStatus = useCallback(
    (item: Suggestion, status: ListStatus) =>
      setChoice((current) => ({
        ...current,
        [item.id]: { status, download: downloadsByDefault(status) },
      })),
    [],
  )

  const setDownload = useCallback(
    (item: Suggestion, download: boolean) =>
      setChoice((current) => ({
        ...current,
        [item.id]: {
          status: current[item.id]?.status ?? DEFAULT_STATUS,
          download,
        },
      })),
    [],
  )

  const add = useCallback(
    (item: Suggestion) => {
      const { status, download } = settingFor(item)
      return approve(item, status, download)
    },
    [approve, settingFor],
  )

  const refresh = useCallback(async () => {
    clear()
    try {
      const result = await api.refreshDiscovery()
      report(
        result.queued > 0
          ? `Searching again — ${result.queued} job${result.queued === 1 ? '' : 's'} queued. New titles land here when they finish.`
          : 'Nothing to search: connect a list provider in Settings first.',
      )
    } catch (failure) {
      reportFailure(failure)
    }
  }, [clear, report, reportFailure])

  return {
    items: data?.items ?? [],
    total: data?.total ?? 0,
    writeFailures: data?.writeFailures ?? [],
    loaded: data !== null,
    error,
    reload,
    notice: notice.notice,
    busy,
    settingFor,
    setStatus,
    setDownload,
    add,
    dismiss,
    refresh,
  }
}
