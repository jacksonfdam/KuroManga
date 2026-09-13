import { useCallback, useState } from 'react'

import { api, type Suggestion } from '../../lib/api'
import { DEFAULT_STATUS, downloadsByDefault, type ListStatus } from '../../lib/format'
import { useAsyncData } from '../../lib/useAsyncData'
import { useJobEvents } from '../../lib/useEvents'
import { useNotice } from '../../lib/useNotice'

export interface Choice {
  status: ListStatus
  download: boolean
}

interface Feed {
  items: Suggestion[]
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
  const [busy, setBusy] = useState<number | null>(null)
  const { notice, report, fail, reportFailure, clear } = useNotice()

  const load = useCallback(async (): Promise<Feed> => {
    const [items, added] = await Promise.all([api.suggestions('new'), api.suggestions('added')])
    return {
      items,
      // The card is gone by the time LIST_WRITE finishes, so a rejected status
      // or a stale token would otherwise never reach the user. A skipped target
      // is an absence rather than a failure: MangaDex without personal
      // credentials is the default setup and has nothing to say here.
      writeFailures: added.filter((item) =>
        item.write_results.some((result) => !result.ok && !result.skipped),
      ),
    }
  }, [])

  const { data, error, reload } = useAsyncData(load)
  useJobEvents(reload)

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
    async (item: Suggestion) => {
      const { status, download } = settingFor(item)
      setBusy(item.id)
      clear()
      try {
        const result = await api.addSuggestion(item.id, status, download)
        // The card goes away either way, so this is the only moment left to say
        // the mapping is pending: nothing downloads until a source is confirmed.
        if (result.needs_review) {
          fail(
            `${item.title}: no source was reliable enough. The series is waiting in Review — confirm the source there${
              download ? ' and the download starts' : ''
            }.`,
          )
        } else {
          report(
            `${item.title} added.${
              download
                ? ' Its chapters are queued under Downloads.'
                : ' Nothing is downloading — start it from the series page when you want it.'
            }`,
          )
        }
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

  const dismiss = useCallback(
    async (item: Suggestion) => {
      setBusy(item.id)
      clear()
      try {
        await api.dismissSuggestion(item.id)
        onChanged()
        reload()
      } catch (failure) {
        reportFailure(failure)
      } finally {
        setBusy(null)
      }
    },
    [clear, onChanged, reload, reportFailure],
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
    writeFailures: data?.writeFailures ?? [],
    loaded: data !== null,
    error,
    reload,
    notice,
    busy,
    settingFor,
    setStatus,
    setDownload,
    add,
    dismiss,
    refresh,
  }
}
