import { useEffect, useRef } from 'react'

type Handler = (event: { event: string; job_id: number; pct: number | null; message: string }) => void

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
