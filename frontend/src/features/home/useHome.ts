import { useCallback } from 'react'

import { api, type ContinueReadingEntry, type DashboardSuggestion } from '../../lib/api'
import { DEFAULT_STATUS, downloadsByDefault } from '../../lib/format'
import { syncLists } from '../../lib/sync'
import { useAsyncData } from '../../lib/useAsyncData'
import { useJobEvents } from '../../lib/useEvents'
import { useNotice } from '../../lib/useNotice'
import { useSuggestionActions } from '../../lib/useSuggestionActions'

/** Progress moved, so what is left of the series moved with it. */
function advanced(row: ContinueReadingEntry, next: number): ContinueReadingEntry {
  return {
    ...row,
    progress: next,
    chapters_remaining:
      row.total_chapters === null ? null : Math.max(row.total_chapters - next, 0),
  }
}

/**
 * The whole screen from one request.
 *
 * Every counter, both columns and the storage panel read the same payload, so
 * they cannot disagree with each other — the counter saying five downloads are
 * running and the activity panel listing three is the bug a screen assembled
 * from six requests eventually shows.
 */
export function useHome(onChanged: () => void) {
  const load = useCallback(() => api.dashboard(), [])
  const { data, error, reload, setData } = useAsyncData(load)
  const notice = useNotice()
  const { report, fail, reportFailure, clear } = notice

  // The shell's badges count the same mappings and suggestions this screen
  // does, so answering one here has to move both.
  const changed = useCallback(() => {
    onChanged()
    reload()
  }, [onChanged, reload])

  const { busy, approve, dismiss } = useSuggestionActions(notice, changed)

  // Progress ticks arrive over the existing SSE subscription and only move a
  // bar, so they patch the running job in place. Anything else (done, failed,
  // retry) moves a job between the two lists and changes counters besides, so
  // it costs a reload.
  useJobEvents((event) => {
    setData((current) =>
      current
        ? {
            ...current,
            activity: {
              ...current.activity,
              running: current.activity.running.map((job) =>
                job.id === event.job_id
                  ? { ...job, pct: event.pct ?? job.pct, last_message: event.message || job.last_message }
                  : job,
              ),
            },
          }
        : current,
    )
    if (event.event !== 'job.progress') reload()
  })

  /**
   * Apply, then confirm — the same contract the library's +1 keeps. A rejected
   * write restores the previous number visibly and says why: the refusals this
   * can hit are a chapter past what the series is known to have and a number
   * that would move a list backwards, and both read as a broken button
   * otherwise.
   */
  const increment = useCallback(
    async (seriesId: number, next: number) => {
      let previous: ContinueReadingEntry[] = []
      clear()
      setData((current) => {
        if (!current) return current
        previous = current.continue_reading
        return {
          ...current,
          continue_reading: current.continue_reading.map((row) =>
            row.series_id === seriesId ? advanced(row, next) : row,
          ),
        }
      })
      try {
        await api.setProgress(seriesId, next)
      } catch (failure) {
        setData((current) => (current ? { ...current, continue_reading: previous } : current))
        reportFailure(failure)
        throw failure
      }
      reload()
    },
    [clear, reload, reportFailure, setData],
  )

  const forceScan = useCallback(async () => {
    clear()
    const failures = await syncLists()
    if (failures.length > 0) fail(failures.join(' · '))
    else report('Scan queued for MyAnimeList and AniList. New chapters land here as the jobs finish.')
  }, [clear, fail, report])

  // One click, no picker: a highlight is a glance, and the screen that asks
  // the two questions properly is Discovery.
  const approveHighlight = useCallback(
    (item: DashboardSuggestion) =>
      approve(item, DEFAULT_STATUS, downloadsByDefault(DEFAULT_STATUS)),
    [approve],
  )

  return {
    dashboard: data,
    loaded: data !== null,
    error,
    reload,
    notice: notice.notice,
    busy,
    increment,
    forceScan,
    approve: approveHighlight,
    dismiss,
  }
}
