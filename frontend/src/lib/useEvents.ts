import { useEffect, useRef } from 'react'

export interface JobEvent {
  event: string
  job_id: number
  pct: number | null
  message: string
  /** Both are null on `job.progress` ticks and on a job the queue could not
      hand to a handler; only the outcome frames identify what finished. */
  job_type: string | null
  series_id: number | null
}

type Handler = (event: JobEvent) => void

/**
 * Subscribe to the server-sent job stream. The stream is driven by Postgres
 * notifications, so a component that listens does not need to poll.
 */
export function useJobEvents(onEvent: Handler): void {
  const handler = useRef(onEvent)
  handler.current = onEvent

  useEffect(() => {
    const source = new EventSource('/api/events')
    const forward = (raw: MessageEvent) => {
      try {
        handler.current(JSON.parse(raw.data))
      } catch {
        // A malformed frame is not worth tearing the stream down for.
      }
    }
    for (const name of ['job.progress', 'job.done', 'job.failed', 'job.retry']) {
      source.addEventListener(name, forward as EventListener)
    }
    return () => source.close()
  }, [])
}
