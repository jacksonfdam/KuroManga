import { useCallback, useEffect, useState } from 'react'

import { api, type Job, type JobEvent } from '../../lib/api'
import { useJobEvents } from '../../lib/useEvents'

// Chapter jobs read as "Series · Ch.N"; everything else (list_sync,
// komga_scan, ...) has no chapter of its own, so it falls back to the job type.
export function jobLabel(job: Job): string {
  if (job.chapter_number !== null) {
    return `${job.series_title ?? 'unknown'} · Ch.${job.chapter_number}`
  }
  return job.series_title ?? job.type
}

export function useDownloads() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [openJob, setOpenJob] = useState<number | null>(null)
  const [events, setEvents] = useState<JobEvent[]>([])

  const load = useCallback(() => {
    api.jobs().then(setJobs).catch(() => undefined)
    api.jobCounts().then(setCounts).catch(() => undefined)
  }, [])

  useEffect(load, [load])

  // Progress arrives over the existing SSE subscription (see useEvents.ts,
  // backed by pg_notify) — nothing here polls. A non-progress event (done,
  // failed, retry) can move a job between sections, so those trigger a full
  // reload rather than a patch of the row that's about to be in the wrong list.
  useJobEvents((event) => {
    setJobs((previous) =>
      previous.map((job) =>
        job.id === event.job_id
          ? { ...job, pct: event.pct ?? job.pct, last_message: event.message || job.last_message }
          : job,
      ),
    )
    if (event.event !== 'job.progress') load()
  })

  useEffect(() => {
    if (openJob === null) return
    api.jobEvents(openJob).then(setEvents).catch(() => undefined)
  }, [openJob])

  const toggle = useCallback((id: number) => {
    setOpenJob((current) => (current === id ? null : id))
  }, [])

  const retry = useCallback((id: number) => {
    api.retry(id).then(load)
  }, [load])

  return { jobs, counts, openJob, events, toggle, retry }
}
