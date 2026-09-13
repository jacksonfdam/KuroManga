import { useEffect, useState } from 'react'

import { api, type Job, type JobEvent } from '../api'
import { useJobEvents } from '../useEvents'

function label(job: Job): string {
  if (job.chapter_number !== null) {
    return `${job.series_title ?? 'unknown'} · Ch.${job.chapter_number}`
  }
  return job.series_title ?? job.type
}

export function Downloads() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [openJob, setOpenJob] = useState<number | null>(null)
  const [events, setEvents] = useState<JobEvent[]>([])

  const load = () => {
    api.jobs().then(setJobs).catch(() => undefined)
    api.jobCounts().then(setCounts).catch(() => undefined)
  }

  useEffect(load, [])
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

  const running = jobs.filter((job) => job.state === 'leased')
  const failed = jobs.filter((job) => job.state === 'failed')
  const pending = jobs.filter((job) => job.state === 'pending')

  return (
    <>
      <h1>Downloads</h1>
      <p className="sub">
        {counts.leased ?? 0} running · {counts.pending ?? 0} pending · {counts.failed ?? 0} failed ·{' '}
        {counts.done ?? 0} done
      </p>

      <h2>Running</h2>
      {running.length === 0 ? (
        <div className="panel empty">Nothing running.</div>
      ) : (
        <div className="panel">
          <table>
            <thead>
              <tr>
                <th>Job</th>
                <th style={{ width: '35%' }}>Progress</th>
                <th>Last line</th>
              </tr>
            </thead>
            <tbody>
              {running.map((job) => (
                <tr key={job.id} onClick={() => setOpenJob(job.id)} style={{ cursor: 'pointer' }}>
                  <td>{label(job)}</td>
                  <td>
                    <div className="bar">
                      <span style={{ width: `${job.pct ?? 0}%` }} />
                    </div>
                  </td>
                  <td className="meta">{job.last_message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2>Failed</h2>
      {failed.length === 0 ? (
        <div className="panel empty">No failures.</div>
      ) : (
        <div className="panel">
          <table>
            <thead>
              <tr>
                <th>Job</th>
                <th>Attempts</th>
                <th>Error</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {failed.map((job) => (
                <tr key={job.id}>
                  <td onClick={() => setOpenJob(job.id)} style={{ cursor: 'pointer' }}>
                    {label(job)}
                  </td>
                  <td>
                    {job.attempts}/{job.max_attempts}
                  </td>
                  <td className="row-error">{(job.last_error ?? '').slice(0, 300)}</td>
                  <td>
                    <button onClick={() => api.retry(job.id).then(load)}>Retry</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2>Pending ({pending.length})</h2>
      <div className="panel">
        {pending.slice(0, 25).map((job) => (
          <div key={job.id} className="meta" style={{ justifyContent: 'space-between' }}>
            <span>{label(job)}</span>
            <span>{job.type}</span>
          </div>
        ))}
        {pending.length === 0 && <div className="empty">Queue is empty.</div>}
      </div>

      {openJob !== null && (
        <>
          <h2>
            Job {openJob} log <button onClick={() => setOpenJob(null)}>close</button>
          </h2>
          <div className="log">
            {events.map((event, index) => (
              <div key={index} style={event.level === 'error' ? { color: 'var(--bad)' } : undefined}>
                {event.ts.slice(11, 19)} {event.pct !== null ? `${Math.round(event.pct)}% ` : ''}
                {event.message}
              </div>
            ))}
            {events.length === 0 && 'no events'}
          </div>
        </>
      )}
    </>
  )
}
