import type { ReviewQueueItem } from '../../lib/api'

const STORE_KEY = 'review:skipped'

/**
 * Skipping is a deferral, not an answer, so it is kept where deferrals belong:
 * in the browser session, not on the series row.
 *
 * `sessionStorage` rather than component state because the queue is cleared in
 * sittings — a trip to Library and back, or a reload after a sync, would
 * otherwise put the title the user just deferred straight back in front of
 * them, which is the whole complaint. It is deliberately not `localStorage`:
 * next week's answer to "is there a source for this yet" is not this week's,
 * and a deferral that outlived the session would quietly become an ignore
 * nobody can see or undo.
 *
 * Every accessor is guarded. A private window, or site data cleared mid-session,
 * throws on read and on write — and a screen that cannot remember a skip must
 * still let the user make one.
 */
export function readSkipped(): number[] {
  try {
    const stored: unknown = JSON.parse(sessionStorage.getItem(STORE_KEY) ?? '[]')
    return Array.isArray(stored) ? stored.filter((id): id is number => typeof id === 'number') : []
  } catch {
    return []
  }
}

export function writeSkipped(ids: number[]): void {
  try {
    sessionStorage.setItem(STORE_KEY, JSON.stringify(ids))
  } catch {
    // Nothing to tell the user: the skip itself still works for this screen,
    // it just will not survive the next load.
  }
}

/**
 * The queue in the order the screen walks it: what the server sent, minus the
 * deferred ones, then the deferred ones in the order they were deferred.
 *
 * Ids that are no longer in the queue drop out on their own — a series that
 * was skipped and then confirmed leaves a number behind in the session, and
 * looking it up here is what keeps that number from becoming a gap.
 */
export function arrange(items: ReviewQueueItem[], skipped: number[]): ReviewQueueItem[] {
  const deferred = new Set(skipped)
  const byId = new Map(items.map((item) => [item.id, item]))
  return [
    ...items.filter((item) => !deferred.has(item.id)),
    ...skipped.map((id) => byId.get(id)).filter((item) => item !== undefined),
  ]
}
