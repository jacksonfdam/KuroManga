export type ListStatus = 'reading' | 'plan_to_read' | 'completed' | 'on_hold' | 'dropped'

export const STATUS_TONE: Record<ListStatus, 'secondary' | 'primary' | 'tertiary' | 'warning' | 'error'> = {
  reading: 'secondary',
  completed: 'primary',
  plan_to_read: 'tertiary',
  on_hold: 'warning',
  dropped: 'error',
}

export const STATUS_LABEL: Record<ListStatus, string> = {
  reading: 'Reading',
  plan_to_read: 'Plan to read',
  completed: 'Completed',
  on_hold: 'On hold',
  dropped: 'Dropped',
}

/**
 * The order the five statuses are offered in. STATUS_LABEL is a map and a map
 * has no order, so the picker needs this list — but it must not carry labels of
 * its own, or the two would drift a wording at a time.
 *
 * The two controls every "add this to my lists" card carries live here for the
 * same reason: a suggestion and a searched-for title are the same decision, and
 * the screens would otherwise drift apart one default at a time.
 */
export const STATUS_ORDER: ListStatus[] = [
  'reading',
  'plan_to_read',
  'completed',
  'on_hold',
  'dropped',
]

// A suggestion is something the user has not started, so the default status
// must not claim otherwise.
export const DEFAULT_STATUS: ListStatus = 'plan_to_read'

// Only what is being read now downloads unasked. Planning to read something is
// not asking for its whole backlog on disk tonight.
export const DOWNLOADS_BY_DEFAULT: ListStatus[] = ['reading']

export const downloadsByDefault = (status: ListStatus): boolean =>
  DOWNLOADS_BY_DEFAULT.includes(status)

/** Chapter numbers are decimals. 12.00 reads as 12; 12.50 must stay 12.5. */
export function formatChapter(value: number): string {
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(2)))
}

// Providers spell this in their own vocabulary (MANGA, ONE_SHOT, manhwa, ...).
// The screen shows one consistent case regardless of which provider it came from.
// AniList and MyAnimeList both use this vocabulary raw; a screen that shows it
// unmapped shows the user a provider's own enum member instead of a sentence.
export const PUBLISHING_LABELS: Record<string, string> = {
  FINISHED: 'Finished',
  RELEASING: 'Releasing',
  NOT_YET_RELEASED: 'Not yet released',
  HIATUS: 'On hiatus',
  CANCELLED: 'Cancelled',
}

export function formatSeriesFormat(value: string | null): string | null {
  if (!value) return null
  return value
    .toLowerCase()
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

// The API reports the provider by its internal slug (`mal`, `anilist`, ...);
// the library screen's sync badges need the name a reader actually recognises.
export const PROVIDER_LABEL: Record<string, string> = {
  mal: 'MAL',
  anilist: 'AniList',
  mangadex: 'MangaDex',
  comick: 'Comick',
  komga: 'Komga',
}

export function formatProviders(providers: string[]): string {
  return providers.map((provider) => PROVIDER_LABEL[provider] ?? provider).join(' / ')
}

export function relativeTime(iso: string): string {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000)
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ['second', 60], ['minute', 60], ['hour', 24], ['day', 7], ['week', 4.35], ['month', 12],
  ]
  let value = seconds
  for (const [unit, step] of units) {
    if (Math.abs(value) < step) {
      return new Intl.RelativeTimeFormat('en', { numeric: 'auto' }).format(-Math.round(value), unit)
    }
    value /= step
  }
  return new Intl.RelativeTimeFormat('en', { numeric: 'auto' }).format(-Math.round(value), 'year')
}

export function formatBytes(bytes: number): string {
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value.toFixed(value >= 100 || unit === 0 ? 0 : 2)} ${units[unit]}`
}
