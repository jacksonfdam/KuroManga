import { useCallback, useEffect, useMemo, useState } from 'react'

import { api, type Job, type JobEvent } from '../../lib/api'
import { useAsyncData } from '../../lib/useAsyncData'
import { useJobEvents } from '../../lib/useEvents'
import { useNotice } from '../../lib/useNotice'
import { useUrlState } from '../../lib/useUrlState'

// Chapter jobs read as "Series · Ch.N". Everything else (list_sync,
// komga_scan, ...) has neither, and gets no label at all: JobRow renders the
// job type right beside this, so falling back to it printed "list_sync
// list_sync" on one line.
export function jobLabel(job: Job): string | null {
  if (job.chapter_number !== null) {
    return `${job.series_title ?? 'unknown'} · Ch.${job.chapter_number}`
  }
  return job.series_title
}

interface Queue {
  jobs: Job[]
  counts: Record<string, number>
}

/** One series' waiting work, which is the unit the queue controls act on. */
export interface QueueGroup {
  seriesId: number | null
  title: string
  jobs: Job[]
}

export type Grouping = 'series' | 'flat'
const GROUPINGS: readonly Grouping[] = ['series', 'flat']

export function useDownloads() {
  const [grouping, setGrouping] = useUrlState<Grouping>('group', 'series', GROUPINGS)
  const [openJob, setOpenJob] = useState<number | null>(null)
  const [events, setEvents] = useState<JobEvent[]>([])
  const { notice, report, reportFailure } = useNotice()

  const load = useCallback(async (): Promise<Queue> => {
    const [jobs, counts] = await Promise.all([api.jobs(), api.jobCounts()])
    return { jobs, counts }
  }, [])

  const { data, error, reload, setData } = useAsyncData(load)

  // Progress arrives over the existing SSE subscription (see useEvents.ts,
  // backed by pg_notify) — nothing here polls. A non-progress event (done,
  // failed, retry) can move a job between sections, so those trigger a full
  // reload rather than a patch of the row that's about to be in the wrong list.
  useJobEvents((event) => {
    setData((current) =>
      current
        ? {
            ...current,
            jobs: current.jobs.map((job) =>
              job.id === event.job_id
                ? { ...job, pct: event.pct ?? job.pct, last_message: event.message || job.last_message }
                : job,
            ),
          }
        : current,
    )
    if (event.event !== 'job.progress') reload()
  })

  useEffect(() => {
    if (openJob === null) return
    api.jobEvents(openJob).then(setEvents).catch(reportFailure)
  }, [openJob, reportFailure])

  const toggle = useCallback((id: number) => {
    setOpenJob((current) => (current === id ? null : id))
  }, [])

  const retry = useCallback(
    (id: number) => {
      api
        .retry(id)
        .then((result) => {
          // Not an error, and not silence either: an equivalent job is already
          // waiting, so the work will happen and the row simply does not move.
          // Saying nothing here reads as a button that did nothing.
          if (!result.retried) report('That work is already queued — this job stays as it is.')
          return reload()
        })
        .catch(reportFailure)
    },
    [reload, report, reportFailure],
  )

  const jobs = useMemo(() => data?.jobs ?? [], [data])

  // Waiting work, gathered by the series it belongs to, because that is what
  // the controls act on: a queue is cancelled or promoted per series, never
  // per job. Jobs with no series (a list sync, a suggestion build) gather
  // under one heading rather than each pretending to be a series of its own.
  const pendingBySeries = useMemo<QueueGroup[]>(() => {
    const groups = new Map<number | null, QueueGroup>()
    for (const job of jobs) {
      if (job.state !== 'pending') continue
      const key = job.series_id
      const existing = groups.get(key)
      if (existing) {
        existing.jobs.push(job)
        continue
      }
      groups.set(key, {
        seriesId: key,
        title: job.series_title ?? 'Work with no series',
        jobs: [job],
      })
    }
    // Biggest first: a series with nine chapters waiting is the one a reader
    // came to this screen about.
    return [...groups.values()].sort((a, b) => b.jobs.length - a.jobs.length)
  }, [jobs])

  const running = useMemo(() => jobs.filter((job) => job.state === 'leased'), [jobs])

  /** Running jobs per lane. The lanes exist so downloads cannot crowd out the
      rest, and this is where that becomes visible instead of merely true. */
  const runningByLane = useMemo(() => {
    const byLane: Record<string, number> = {}
    for (const job of running) byLane[job.lane] = (byLane[job.lane] ?? 0) + 1
    return byLane
  }, [running])

  const retryFailed = useCallback(() => {
    api
      .retryFailed()
      .then((result) => {
        report(
          result.requeued === 0
            ? 'Nothing to retry — every failure left is one a second attempt cannot change.'
            : `Requeued ${result.requeued} ${result.requeued === 1 ? 'job' : 'jobs'}.`,
        )
        return reload()
      })
      .catch(reportFailure)
  }, [reload, report, reportFailure])

  const promote = useCallback(
    (seriesId: number, title: string) => {
      api
        .promoteQueue(seriesId)
        .then((result) => {
          report(`${title} moved to the front — ${result.moved} waiting.`)
          return reload()
        })
        .catch(reportFailure)
    },
    [reload, report, reportFailure],
  )

  const cancel = useCallback(
    (seriesId: number, title: string) => {
      api
        .cancelQueue(seriesId)
        .then((result) => {
          // Only waiting work goes. Anything already running keeps running,
          // and saying so stops the count reading as a mistake.
          report(
            `Dropped ${result.dropped} waiting ${result.dropped === 1 ? 'job' : 'jobs'} for ${title}. Anything already running finishes.`,
          )
          return reload()
        })
        .catch(reportFailure)
    },
    [reload, report, reportFailure],
  )

  return {
    jobs,
    pendingBySeries,
    running,
    runningByLane,
    grouping,
    setGrouping,
    retryFailed,
    promote,
    cancel,
    counts: data?.counts ?? {},
    loaded: data !== null,
    error,
    reload,
    notice,
    openJob,
    events,
    toggle,
    retry,
  }
}
