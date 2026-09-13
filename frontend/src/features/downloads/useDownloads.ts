import { useCallback, useEffect, useState } from 'react'

import { api, type Job, type JobEvent } from '../../lib/api'
import { useAsyncData } from '../../lib/useAsyncData'
import { useJobEvents } from '../../lib/useEvents'
import { useNotice } from '../../lib/useNotice'

// Chapter jobs read as "Series · Ch.N"; everything else (list_sync,
// komga_scan, ...) has no chapter of its own, so it falls back to the job type.
export function jobLabel(job: Job): string {
  if (job.chapter_number !== null) {
    return `${job.series_title ?? 'unknown'} · Ch.${job.chapter_number}`
  }
  return job.series_title ?? job.type
}

interface Queue {
  jobs: Job[]
  counts: Record<string, number>
}

export function useDownloads() {
  const [openJob, setOpenJob] = useState<number | null>(null)
  const [events, setEvents] = useState<JobEvent[]>([])
  const { notice, reportFailure } = useNotice()

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
      api.retry(id).then(reload).catch(reportFailure)
    },
    [reload, reportFailure],
  )

  return {
    jobs: data?.jobs ?? [],
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
