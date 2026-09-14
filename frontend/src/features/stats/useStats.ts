import { useCallback, useState } from 'react'

import { api, type StatsPeriodKey } from '../../lib/api'
import { useAsyncData } from '../../lib/useAsyncData'
import { useJobEvents } from '../../lib/useEvents'

/**
 * The whole screen from one request, re-asked when the period changes.
 *
 * Every figure here is windowed by the endpoint, so the period belongs in the
 * request and not in a filter over a payload the screen already has — the
 * velocity buckets in particular cannot be reconstructed from a different
 * window's answer.
 */
export function useStats() {
  const [period, setPeriod] = useState<StatsPeriodKey>('30d')
  const load = useCallback(() => api.stats(period), [period])
  const { data, error, reload } = useAsyncData(load)

  // A finished job moves what this screen reports: a download changes the
  // chapters on disk, a progress write adds an event to the velocity log.
  // Progress ticks only move a bar elsewhere and change none of these
  // aggregates, so they are ignored rather than costing a request each.
  useJobEvents((event) => {
    if (event.event !== 'job.progress') reload()
  })

  return { stats: data, loaded: data !== null, error, reload, period, setPeriod }
}
