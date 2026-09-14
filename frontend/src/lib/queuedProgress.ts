import { useCallback, useSyncExternalStore } from 'react'

import type { JobEvent } from './useEvents'

/**
 * The gap between "the queue took the chapter" and "the database has it".
 *
 * `POST /series/{id}/progress` only enqueues a PROGRESS_WRITE; the number every
 * screen reads comes from list_entry, which the handler advances when the job
 * runs. A screen that reloads on the queue-accept therefore reads the old
 * chapter straight back and the click looks like it missed — the defect this
 * exists to stop. A screen that never reloads has the opposite one: it shows a
 * chapter the providers may never have received.
 *
 * So the accepted chapter is held here instead of being written into the loaded
 * data. Reloads keep landing and keep being honest; this sits on top of them
 * until the stored number catches up, at which point it stops applying on its
 * own — there is nothing to expire and no timer to get wrong.
 *
 * It is module state rather than a hook's, because the same +1 is offered by
 * the library grid, the library table, both continue-reading rows and the
 * series screen. Per-screen state would mean walking from Home to Library
 * dropped the chapter back to the stored one with nothing to explain it — the
 * same silent revert, one navigation later.
 */
interface Queued {
  chapter: number
  /** Carried so the shell can name the series when a write is refused; the
      screen that reports it may not be the screen the click came from. */
  title: string
}

export interface QueuedProgress {
  /**
   * The chapter this series is waiting on, or null when `stored` already
   * covers it. Self-clearing: once a reload brings the written number back,
   * the entry stops applying without anyone having to remove it.
   */
  awaiting: (seriesId: number, stored: number) => number | null
  /** Record a chapter the queue accepted. */
  queue: (seriesId: number, chapter: number, title: string) => void
  /** Forget one: the write was refused, so the stored number is the truth. */
  drop: (seriesId: number) => void
}

const PROGRESS_WRITE = 'progress_write'

let queued: ReadonlyMap<number, Queued> = new Map()
const listeners = new Set<() => void>()

function publish(next: ReadonlyMap<number, Queued>): void {
  queued = next
  for (const listener of listeners) listener()
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

// Read from the module variable rather than from a render's copy, so two
// clicks in the same tick do not overwrite each other.
const snapshot = (): ReadonlyMap<number, Queued> => queued

function remember(seriesId: number, chapter: number, title: string): void {
  publish(new Map(queued).set(seriesId, { chapter, title }))
}

function forget(seriesId: number): void {
  if (!queued.has(seriesId)) return
  const next = new Map(queued)
  next.delete(seriesId)
  publish(next)
}

export function useQueuedProgress(): QueuedProgress {
  const rows = useSyncExternalStore(subscribe, snapshot)

  const awaiting = useCallback(
    (seriesId: number, stored: number) => {
      const entry = rows.get(seriesId)
      return entry !== undefined && entry.chapter > stored ? entry.chapter : null
    },
    [rows],
  )

  return { awaiting, queue: remember, drop: forget }
}

/**
 * A PROGRESS_WRITE that gave up is the only way a queued chapter can be known
 * to be dead: every other outcome either advances the stored number or leaves
 * the job still trying. Returns what to tell the user, or null when the event
 * says nothing about a chapter anyone is waiting on.
 *
 * job.retry is deliberately not handled — the job is going to run again, and
 * dropping the chapter there would report a failure that has not happened.
 *
 * Called from the shell rather than from a screen, because the failure can
 * land while the user is somewhere else entirely and a notice nobody is
 * mounted to show is a number that falls back for no stated reason.
 */
export function settleQueuedProgress(event: JobEvent): string | null {
  if (event.event !== 'job.failed' || event.job_type !== PROGRESS_WRITE) return null
  const seriesId = event.series_id
  if (seriesId === null) return null
  const entry = queued.get(seriesId)
  if (entry === undefined) return null
  forget(seriesId)
  return `Couldn't write chapter ${entry.chapter} of ${entry.title} to your lists. The number is back to what they hold.`
}
