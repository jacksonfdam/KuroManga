import { type ListStatusValue } from './lib/api'

/**
 * The two controls every "add this to my lists" card carries. They live here
 * because a suggestion and a searched-for title are the same decision, and the
 * screens would otherwise drift apart one default at a time.
 */
export const STATUSES: { value: ListStatusValue; label: string }[] = [
  { value: 'reading', label: 'Reading' },
  { value: 'plan_to_read', label: 'Plan to read' },
  { value: 'completed', label: 'Completed' },
  { value: 'on_hold', label: 'On hold' },
  { value: 'dropped', label: 'Dropped' },
]

// A suggestion is something the user has not started, so the default status
// must not claim otherwise.
export const DEFAULT_STATUS: ListStatusValue = 'plan_to_read'

// Only what is being read now downloads unasked. Planning to read something is
// not asking for its whole backlog on disk tonight.
export const DOWNLOADS_BY_DEFAULT: ListStatusValue[] = ['reading']

export const downloadsByDefault = (status: ListStatusValue): boolean =>
  DOWNLOADS_BY_DEFAULT.includes(status)
