import type { StatsPeriodKey } from '../../lib/api'

/** The four windows the endpoint accepts. Anything else is a 422 rather than
 * a silent fallback, so the screen offers exactly these and no more. */
export const PERIODS: { key: StatsPeriodKey; label: string }[] = [
  { key: '7d', label: '7 days' },
  { key: '30d', label: '30 days' },
  { key: '90d', label: '90 days' },
  { key: '365d', label: '365 days' },
]

/**
 * The payload's dates are plain calendar days, and the buckets behind them
 * were counted in UTC. Parsed as local time they slide to the day before for
 * anyone west of UTC, which would date the busiest day wrong by one.
 */
function utcDay(iso: string): Date {
  return new Date(`${iso}T00:00:00Z`)
}

export function formatDay(iso: string): string {
  return utcDay(iso).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  })
}

/** The axis form: a year under every tick is noise when both ends share it. */
export function formatShortDay(iso: string): string {
  return utcDay(iso).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  })
}

/** Minutes the way a person says them: `45 min`, `3h 05m`, `7d 17h`. */
export function formatMinutes(total: number): string {
  if (total <= 0) return '0 min'
  if (total < 60) return `${total} min`
  const hours = Math.floor(total / 60)
  if (hours < 24) return `${hours}h ${String(total % 60).padStart(2, '0')}m`
  return `${Math.floor(hours / 24)}d ${hours % 24}h`
}

/**
 * "3,720". Chapter figures are decimals in the database (a half chapter is a
 * real delta), so the separator has to survive a fraction rather than assume
 * an integer.
 */
export function grouped(value: number): string {
  return value.toLocaleString('en-GB', { maximumFractionDigits: 2 })
}

/** Which path recorded the reading — the two sources progress_event stores. */
export const SOURCE_PHRASE: Record<string, string> = {
  komga: 'through Komga',
  manual: 'entered by hand',
}
