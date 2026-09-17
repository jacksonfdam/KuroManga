import type { ListStatus } from './format'

export type SeriesState = 'mapped' | 'needs_review' | 'downloading' | 'failed'

export interface Series {
  id: number
  title: string
  slug: string
  cover_url: string | null
  source_site: string | null
  source_url: string | null
  providers: string[]
  /** Whether a progress or status write has anywhere to land. False for a
      series held only by read-only providers, where every write must fail. */
  writable: boolean
  downloaded: number
  known: number
  in_flight: number
  failed: number
  total_chapters: number | null
  auto_download: boolean
  state: SeriesState
  status: ListStatus | null
  progress: number
  score: number | null
  genres: string[]
  format: string | null
  updated_at: string | null
  /** Komga's own id for the series, once a scan has matched it. */
  komga_series_id: string | null
}

export interface Candidate {
  id: number
  source_site: string
  source_url: string
  title: string
  cover_url: string | null
  chapter_count: number | null
  year: number | null
  score: number
}

export interface SeriesChapter {
  number: number
  title: string | null
  state: string
  file_path: string | null
  /** Komga's own id for the book, once it has indexed the downloaded file. */
  komga_book_id: string | null
}

export interface SeriesEntry {
  provider: string
  provider_media_id: string
  status: ListStatus | null
  user_progress_chapter: number
  updated_at: string | null
}

export interface SeriesCredit {
  role: string
  name: string
}

export interface SeriesCharacter {
  name: string
  role: string | null
  image_url: string | null
}

export interface SimilarWork {
  media_id: string
  title: string | null
  cover_url: string | null
  score: number | null
  chapters: number | null
  genres: string[]
  /** The series in this library that is the same work, if there is one. */
  series_id: number | null
}

/**
 * Everything the detail screen shows that is not a column of its own. Every
 * field is nullable because neither provider is a superset of the other: only
 * MyAnimeList names the magazine a series runs in, only AniList reports its
 * country of origin, and a series synced before those fields were requested
 * reports neither. A null here is rendered as an absence, never as a zero.
 */
export interface SeriesMetadata {
  native_title: string | null
  synopsis: string | null
  publisher: string | null
  publication_status:
    | 'releasing'
    | 'finished'
    | 'not_yet_released'
    | 'cancelled'
    | 'hiatus'
    | null
  start_year: number | null
  end_year: number | null
  country: string | null
  demographic: string | null
  site_url: string | null
  global_score: number | null
  vote_count: number | null
  rank: number | null
  popularity: number | null
  favourites: number | null
  user_score: number | null
  volumes_total: number | null
  volumes_read: number | null
  reread_count: number | null
  started_at: string | null
  completed_at: string | null
  list_updated_at: string | null
  notes: string | null
  user_tags: string[]
  credits: SeriesCredit[]
  characters: SeriesCharacter[]
  similar: SimilarWork[]
  providers: string[]
  enriched_at: string | null
}

export interface ReadingFrequencyWeekday {
  weekday: number
  label: string
  chapters: number
}

/**
 * `progress_event` fills forward only from 2026-09-13, so `first_event_at`
 * null means this series has never had a recorded event — not that the week
 * was quiet. The seven weekday buckets are still always present and zero
 * where nothing landed, because inside a series that *has* been tracked a
 * zero is a real zero, the same distinction `Velocity` draws for the log as
 * a whole.
 */
export interface SeriesReadingFrequency {
  weekdays: ReadingFrequencyWeekday[]
  total_chapters: number
  active_days: number
  busiest_weekday: number | null
  first_event_at: string | null
}

export interface SeriesDetail {
  series: Series
  metadata: SeriesMetadata
  mapping: { source_site: string; source_url: string } | null
  chapters: SeriesChapter[]
  entries: SeriesEntry[]
  reading_minutes_per_chapter: number
  /** Where Komga is served to a browser. Empty until it is configured. */
  komga_public_url: string
  reading_frequency: SeriesReadingFrequency
}

export interface ReviewPayload {
  series: {
    id: number
    title: string
    titles: string[]
    english: string[]
    romaji: string[]
    cover_url: string | null
  }
  candidates: Candidate[]
}

/**
 * One series waiting in the review queue.
 *
 * Everything a scannable row needs and nothing more: the candidates are a
 * request of their own, and fetching 168 sets of them to draw a list nobody
 * has read yet is how a screen that exists to move fast stops moving.
 */
export interface ReviewQueueItem {
  id: number
  title: string
  cover_url: string | null
  candidate_count: number
}

/** `total` is the length of `items`, counted from the same rows — the screen
    numbers a series "3 of 168" out of this list, so a total it cannot account
    for would be a position past the end of it. */
export interface ReviewQueue {
  total: number
  items: ReviewQueueItem[]
}

export type DiscoverKind = 'suggestion' | 'review' | 'unmatched'
export type DiscoverSort = 'rank' | 'title' | '-title' | 'added' | '-added'

export interface DiscoverQuery {
  q: string
  kinds: DiscoverKind[]
  sort: DiscoverSort
  page: number
  per: number
}

export interface DiscoverFeed {
  items: DiscoverItem[]
  total: number
  actionable: number
  page: number
  per: number
  pages: number
}

export interface DiscoverItem {
  kind: DiscoverKind
  id: number
  series_id: number | null
  title: string
  cover_url: string | null
  /** Why this is in front of you: which anime it came from, or that it is on
      your list with no source. */
  why: string
  /** The step owed now, and only that one. What an item owes after it is
      answered depends on the answer, and a card that named the whole journey
      was promising steps this screen has no control for. */
  needs: string[]
  candidates: { url: string; site: string; score: number; chapters?: number }[]
  /** A source good enough to take without a decision. */
  confident: boolean
  candidate_count: number
  /** When it arrived. Null for an unmatched anime: `anime_entry` records only
      when the sync last touched the row, so there is no answer to give. */
  added_at: string | null
}

export interface Job {
  id: number
  type: string
  state: string
  attempts: number
  max_attempts: number
  /** Which worker owns it: 'fetch' or 'download'. Stated by the API rather
      than derived here, so the mapping has one home. */
  lane: string
  last_error: string | null
  /** Whether retrying could ever help. False for an ordinary failure; true for
      one nothing about a second attempt would change. */
  permanent: boolean
  series_id: number | null
  series_title: string | null
  chapter_number: number | null
  chapter_title: string | null
  pct: number | null
  last_message: string | null
  created_at: string | null
  started_at: string | null
  finished_at: string | null
}

export interface JobEvent {
  ts: string
  level: string
  message: string
  pct: number | null
}

export interface SettingsPayload {
  values: Record<string, string>
  providers: Record<string, ProviderStatus>
  sources: Record<string, SourceStatus>
  library_path: string
}

/** An OAuth provider is connected or not; a token provider just needs its
 * environment variable set, so it has no connect/disconnect state at all —
 * and no account name or token expiry to report either. */
export type ProviderStatus =
  | {
      uses_oauth: true
      connected: boolean
      configured: boolean
      account_name?: string
      expires_at?: string | null
    }
  | { uses_oauth: false; configured: boolean }

// The PUT answers with more than the GET: what was ignored, and whether the
// worker has to be restarted for the new schedule to be read. It is not a
// SettingsPayload, and typing it as one is what let the restart flag go
// unnoticed.
export interface SettingsSaved {
  ok: boolean
  ignored: string[]
  restart_worker_required: boolean
  values: Record<string, string>
}

export interface Integration {
  name: string
  state: 'ok' | 'unauthenticated' | 'unreachable'
  detail: string | null
}

/**
 * GET /api/dashboard — the Home screen in one request.
 *
 * Six requests to fill one above-the-fold view is fine on localhost and falls
 * apart on a NAS, so the whole screen is one payload. Where the design carries
 * a figure nothing measures — network throughput, per-job CPU, a pool health
 * verdict, the storage split by content type, a suggestion's "resume at
 * chapter N" — the field is absent here rather than zero, and the screen is
 * expected to leave the element out rather than draw a dash.
 */
export interface DashboardIntegrations {
  items: Integration[]
  connected: number
  total: number
}

export interface ActiveReading {
  series: number
  /** Of those, how many have a chapter the pipeline knows about beyond progress. */
  with_unread: number
  /** Of those, how many have one on disk — a different fact from with_unread. */
  readable_now: number
}

export interface DownloadCounts {
  in_flight: number
  queued: number
  /** Bounded on purpose: lifetime failures only ever grow. */
  failed_24h: number
  sources: string[]
}

export interface MappingCounts {
  pending: number
  /** Of those, how many are one click from resolved on the Review screen. */
  with_candidates: number
}

export interface DiscoveryCounts {
  new: number
  new_today: number
  /** The anime providers the suggestions came from, not the manga ids'. */
  providers: string[]
}

export interface WorkerState {
  /** `stalled` is a worker that died holding a lease; reclaim picks it up
      within a minute. There is no heartbeat, so `idle` cannot tell a worker
      waiting for work apart from one that is not running at all. */
  state: 'busy' | 'stalled' | 'idle'
  running: number
  expired_leases: number
  last_finished_at: string | null
}

export interface ContinueReadingEntry {
  series_id: number
  /** Whether a progress write has anywhere to land. */
  writable: boolean
  title: string
  slug: string
  cover_url: string | null
  progress: number
  total_chapters: number | null
  /** Null when the total is unknown: 0 reads as "caught up", which is a
      different claim from "nobody said how long this manga is". */
  chapters_remaining: number | null
  known_ahead: number
  downloaded_ahead: number
  in_komga: boolean
  updated_at: string | null
}

export interface DashboardSuggestion {
  id: number
  title: string
  cover_url: string | null
  total_chapters: number | null
  year: number | null
  publishing_status: string | null
  /** 0..1, the order the highlights are picked in. */
  rank_score: number
  series_id: number | null
  best_source: { site: string; url: string; score: number } | null
  reason: {
    origin_provider: string | null
    origin_title: string | null
    origin_status: string | null
    episodes_watched: number | null
    total_episodes: number | null
    relation: string | null
  }
}

/** Absent byte fields, not zeroed ones, so a missing volume cannot render as
    an empty pool. */
export type StorageUsage =
  | {
      path: string
      available: true
      total_bytes: number
      used_bytes: number
      free_bytes: number
      used_pct: number
    }
  | { path: string; available: false; detail: string }

export interface Dashboard {
  generated_at: string
  integrations: DashboardIntegrations
  active_reading: ActiveReading
  downloads: DownloadCounts
  mappings: MappingCounts
  discovery: DiscoveryCounts
  queue: Record<string, number>
  worker: WorkerState
  cron: { id: string; expression: string; valid: boolean; next_run_at: string | null }[]
  continue_reading: ContinueReadingEntry[]
  suggestions: DashboardSuggestion[]
  activity: { running: Job[]; recent: Job[] }
  storage: StorageUsage
}

/**
 * GET /api/stats?period= — the statistics screen.
 *
 * Two fields carry a caveat the screen is required to repeat rather than
 * quietly drop. `velocity.has_history` is false until something is recorded,
 * and an absent chart is an absent log, not a month of reading nothing.
 * `time_spent.estimated` is always true, because nothing in this pipeline
 * watches a clock: the flag travels with the number so that a caption cannot
 * be the only thing carrying it.
 */
export type StatsPeriodKey = '7d' | '30d' | '90d' | '365d'

export interface StatsPeriod {
  key: StatsPeriodKey
  days: number
  /** ISO calendar days, both ends inclusive. */
  from: string
  to: string
}

export interface StatsTotals {
  series: number
  tracked: number
  in_komga: number
  chapters_known: number
  chapters_downloaded: number
  /** Lifetime, summed from where each list says the reader stands. It owes
      nothing to progress_event, so it covers reading done before the log. */
  chapters_read: number
}

export interface VelocityDay {
  date: string
  chapters: number
}

export interface Velocity {
  /** The earliest event ever recorded, or null when there is none. */
  tracking_since: string | null
  has_history: boolean
  /** Whether the buckets can honestly claim the whole period. */
  covers_full_period: boolean
  from: string | null
  to: string | null
  /** Empty — not a run of zeros — when nothing was ever recorded. Inside a
      measured range a zero is a real zero. */
  days: VelocityDay[]
  chapters: number
  days_counted: number
  /** Divided by the days measured, not by the days in the period. */
  per_day: number
  busiest: VelocityDay | null
  /** Which path reported the reading: `komga` or `manual`. */
  by_source: Record<string, number>
}

export interface TimeSpent {
  estimated: true
  /** The formula, in words, as the payload spells it. */
  basis: string
  minutes_per_chapter: number
  period_minutes: number
  recorded_minutes: number
  /** Null means recorded_minutes is zero because nothing was measured, not
      because nothing was read. */
  recorded_from: string | null
  library_minutes: number
}

/** What a batch status apply reports back. `skipped` are series on no list. */
export interface BatchStatusResult {
  ok: boolean
  status: ListStatus
  queued: number
  skipped: number[]
  destinations: string[]
}

export interface Stats {
  period: StatsPeriod
  totals: StatsTotals
  /** All five statuses in enum order, zero-filled. */
  status_distribution: { status: ListStatus; count: number }[]
  top_genres: { genre: string; count: number }[]
  /** The empty decades in between are included: a gap left out of the list
      draws as a narrower bar beside its neighbour instead of as silence. */
  publication_eras: { decade: number; label: string; count: number }[]
  without_publication_year: number
  velocity: Velocity
  time_spent: TimeSpent
}

// Callers that need to tell "the thing you asked for doesn't exist" apart
// from "the request failed" (and show one, not the other) need the status
// code — a plain Error only carries a message a caller would have to
// string-match against.
export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

/**
 * The sentence a user is shown for a rejection. Every screen reports a failure
 * through this, so the wording never depends on which screen made the request.
 */
export function messageOf(failure: unknown): string {
  return failure instanceof Error ? failure.message : String(failure)
}

/** MangaDex has an account; comick has none, so it only reports whether it answers. */
export type SourceStatus =
  | { authenticated: boolean; username: string | null }
  | { reachable: boolean }

export interface SuggestionSource {
  site: string
  url: string
  chapters: number | null
  score: number
}

export interface Suggestion {
  id: number
  title: string
  cover_url: string | null
  total_chapters: number | null
  year: number | null
  publishing_status: string | null
  state: 'new' | 'dismissed' | 'added'
  rank_score: number
  series_id: number | null
  reason: {
    origin_title: string | null
    origin_status: string | null
    total_episodes: number | null
    relation: string | null
  }
  sources: SuggestionSource[]
  best_source: { site: string; url: string; score: number } | null
  write_results: {
    target: string
    ok: boolean
    // A target that has nothing configured to write to, rather than one that failed.
    skipped?: boolean
    error: string | null
    at?: string
  }[]
}

/** One anime from the list that no relation could turn into a manga. */
export interface UnmatchedAnime {
  id: number
  provider: string
  media_id: string
  title: string | null
  title_romaji: string | null
  title_english: string | null
  cover_url: string | null
  total_episodes: number | null
  progress_episode: number
  status: string
  providers: string[]
  hidden: boolean
}

export interface UnmatchedPage {
  total: number
  items: UnmatchedAnime[]
}

export interface AnimeMember {
  provider: string
  media_id: string
  url: string | null
}

/**
 * A relation AniList declared as this anime's SOURCE or ADAPTATION that still
 * cannot become a manga — a light novel, most often. MyAnimeList never asks
 * for anime relations at all, so `provider` is always `"anilist"` here; kept
 * as a plain string anyway since this type mirrors what the wire sends.
 */
export interface DiscardedRelation {
  provider: string
  media_id: string
  relation: string
  title: string
  format: string | null
}

/**
 * The list payload carries only what a row renders; everything else is
 * fetched one anime at a time when the panel opens. There is no *usable*
 * relation list here — both providers drop a relation whose format is not a
 * manga format before it is ever stored, so an anime that reaches this
 * screen has none, by construction. `discarded_relations` is the other half
 * of that same filter, kept instead of dropped: null means this anime has
 * not been through a sync that records it yet, and that is a different fact
 * from the empty array recorded for an anime where AniList declared nothing.
 */
export interface UnmatchedDetail extends UnmatchedAnime {
  synonyms: string[]
  members: AnimeMember[]
  discarded_relations: DiscardedRelation[] | null
}

/** Null when the provider did not say, which the screen has to admit to. */
export type MangaFormat = 'MANGA' | 'MANHWA' | 'MANHUA' | 'OEL'

/** What the database already knows about a candidate, strongest state first. */
export type KnownState = 'added' | 'on_list' | 'dismissed' | 'suggested'

export interface SearchCandidate {
  provider: string
  media_id: string
  alt_ids: Record<string, string>
  providers: string[]
  title: string
  cover_url: string | null
  total_chapters: number | null
  year: number | null
  publishing_status: string | null
  format: MangaFormat | null
  score: number
  known_state: KnownState | null
  series_id: number | null
}

/**
 * `query_unsupported` is the one a retry cannot answer: the provider refuses the
 * query itself, so the screen must not offer to search again.
 */
export type SearchErrorCode =
  | 'not_connected'
  | 'rate_limited'
  | 'provider_error'
  | 'query_unsupported'

export interface SearchProviderError {
  provider: string
  code: SearchErrorCode
  detail: string
}

/** `candidates` and `errors` are independent: one provider down is half an answer. */
export interface UnmatchedSearch {
  anime: UnmatchedAnime
  query: string
  /**
   * What each provider that answered was actually asked, keyed by provider.
   * Usually `query` again - but MyAnimeList sometimes substitutes a name the
   * anime is also known by, or a trimmed prefix, and `query` alone would hide
   * that from the user.
   */
  queries: Record<string, string>
  candidates: SearchCandidate[]
  errors: SearchProviderError[]
}

export interface UnmatchedAdded {
  ok: boolean
  series_id: number
  job_ids: number[]
  needs_review: boolean
  suggestion_id: number
}

export interface HiddenResult {
  ok: boolean
  hidden: boolean
  rows: number
}

/**
 * The sentence out of a rejected response.
 *
 * FastAPI answers a refusal with `{"detail": "..."}` and a failed validation
 * with `{"detail": [{"msg": "...", ...}]}`. Passing the raw body through meant
 * every screen showed a user the JSON — a refused +1 read as
 * `{"detail":"this series is only known to have 30 chapters"}`, braces and all.
 */
function sentenceOf(body: string, response: Response): string {
  try {
    const parsed = JSON.parse(body) as { detail?: unknown }
    const detail = parsed.detail
    if (typeof detail === 'string' && detail) return detail
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => (item as { msg?: unknown }).msg)
        .filter((msg): msg is string => typeof msg === 'string')
      if (messages.length > 0) return messages.join('. ')
    }
  } catch {
    // Not JSON — a proxy error page or an empty body. Fall through.
  }
  return body || `${response.status} ${response.statusText}`
}

export interface Source {
  key: string
  name: string
  template: string
  base_url: string
  lang: string
  nsfw: boolean
  hand_ported: boolean
  version: string
  enabled: boolean
  priority: number
  /** Why this site cannot run, in the API's words. Null when it can. */
  reason: string | null
}

export interface SourcePage {
  items: Source[]
  /** Every row matching the filters, which is not items.length: the catalogue
      is generated output in four figures and the listing is paged. */
  total: number
  page: number
  size: number
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!response.ok) {
    throw new ApiError(sentenceOf(await response.text(), response), response.status)
  }
  return response.json() as Promise<T>
}

export const api = {
  dashboard: () => request<Dashboard>('/api/dashboard'),
  /** Apply one status to many series. One job per series; see routes_series. */
  batchStatus: (seriesIds: number[], status: ListStatus) =>
    request<BatchStatusResult>('/api/series/status', {
      method: 'POST',
      body: JSON.stringify({ series_ids: seriesIds, status }),
    }),
  statusDestinations: () =>
    request<{ destinations: string[] }>('/api/series/status/destinations'),
  stats: (period: StatsPeriodKey) => request<Stats>(`/api/stats?period=${period}`),
  series: (state?: string) =>
    request<Series[]>(`/api/series${state ? `?state=${state}` : ''}`),
  chapters: (id: number) => request<unknown[]>(`/api/series/${id}/chapters`),
  seriesDetail: (id: number) => request<SeriesDetail>(`/api/series/${id}`),
  candidates: (id: number) => request<ReviewPayload>(`/api/series/${id}/candidates`),
  reviewQueue: () => request<ReviewQueue>('/api/series/review/queue'),
  reviewIgnored: () => request<ReviewQueue>('/api/series/review/ignored'),
  // "Stop asking me about this one", and the way back out of it. The series
  // keeps its list entries, its status and its syncs either way — this only
  // ever changes which screen shows it.
  ignoreInReview: (id: number) =>
    request<{ ok: boolean; ignored: boolean }>(`/api/series/${id}/review-ignore`, {
      method: 'POST',
    }),
  unignoreInReview: (id: number) =>
    request<{ ok: boolean; ignored: boolean }>(`/api/series/${id}/review-ignore`, {
      method: 'DELETE',
    }),
  confirmMapping: (id: number, sourceUrl: string) =>
    request<{ ok: boolean }>(`/api/series/${id}/mapping`, {
      method: 'POST',
      body: JSON.stringify({ source_url: sourceUrl }),
    }),
  research: (id: number) =>
    request<{ ok: boolean }>(`/api/series/${id}/search`, { method: 'POST' }),
  setProgress: (id: number, chapter: number) =>
    request<{ progress: number; queued: boolean }>(`/api/series/${id}/progress`, {
      method: 'POST',
      body: JSON.stringify({ chapter }),
    }),
  setAutoDownload: (id: number, enabled: boolean) =>
    request<{ auto_download: boolean; queued: number }>(`/api/series/${id}/auto-download`, {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    }),
  download: (id: number, from?: number, to?: number) =>
    request<{ queued: number }>(`/api/series/${id}/download`, {
      method: 'POST',
      body: JSON.stringify({ from_chapter: from ?? null, to_chapter: to ?? null }),
    }),
  setListStatus: (id: number, status: ListStatus) =>
    request<{ ok: boolean; status: ListStatus; queued: boolean }>(
      `/api/series/${id}/status`,
      { method: 'POST', body: JSON.stringify({ status }) },
    ),
  saveNotes: (id: number, notes: string, tags: string[]) =>
    request<{ ok: boolean; queued: boolean }>(`/api/series/${id}/notes`, {
      method: 'POST',
      body: JSON.stringify({ notes, tags }),
    }),
  jobs: (state?: string) => request<Job[]>(`/api/jobs${state ? `?state=${state}` : ''}`),
  jobCounts: () => request<Record<string, number>>('/api/jobs/counts'),
  jobEvents: (id: number) => request<JobEvent[]>(`/api/jobs/${id}/events`),
  retry: (id: number) =>
    request<{ ok: boolean; retried: boolean; reason: string | null }>(
      `/api/jobs/${id}/retry`,
      { method: 'POST' },
    ),
  removeSeries: (ids: number[]) =>
    request<{ ok: boolean; removed: number }>('/api/series', {
      method: 'DELETE',
      body: JSON.stringify({ ids }),
    }),
  clearFailedJobs: () =>
    request<{ ok: boolean; cleared: number }>('/api/jobs/failed', { method: 'DELETE' }),
  discover: (query: DiscoverQuery) => {
    const params = new URLSearchParams({
      sort: query.sort,
      page: String(query.page),
      per: String(query.per),
    })
    if (query.q) params.set('q', query.q)
    // Repeated rather than comma-joined: the endpoint declares a list of
    // enums, and one value carrying two names would be refused as neither.
    for (const kind of query.kinds) params.append('kind', kind)
    return request<DiscoverFeed>(`/api/discover?${params}`)
  },
  retryFailed: () =>
    request<{ ok: boolean; requeued: number }>('/api/jobs/retry-failed', { method: 'POST' }),
  promoteQueue: (seriesId: number) =>
    request<{ ok: boolean; moved: number }>(`/api/series/${seriesId}/queue/top`, {
      method: 'POST',
    }),
  cancelQueue: (seriesId: number) =>
    request<{ ok: boolean; dropped: number }>(`/api/series/${seriesId}/queue`, {
      method: 'DELETE',
    }),
  sync: (provider: string) =>
    request<{ ok: boolean }>(`/api/sync/${provider}`, { method: 'POST' }),
  settings: () => request<SettingsPayload>('/api/settings'),
  saveSettings: (values: Record<string, string>) =>
    request<SettingsSaved>('/api/settings', {
      method: 'PUT',
      body: JSON.stringify({ values }),
    }),
  authStart: (provider: string) => request<{ url: string }>(`/api/auth/${provider}/start`),
  disconnect: (provider: string) =>
    request<{ ok: boolean }>(`/api/auth/${provider}`, { method: 'DELETE' }),
  sources: (params: {
    q?: string
    lang?: string
    nsfw?: boolean
    enabled?: boolean
    page?: number
  }) => {
    const query = new URLSearchParams()
    if (params.q) query.set('q', params.q)
    if (params.lang) query.set('lang', params.lang)
    if (params.nsfw !== undefined) query.set('nsfw', String(params.nsfw))
    if (params.enabled !== undefined) query.set('enabled', String(params.enabled))
    query.set('page', String(params.page ?? 1))
    return request<SourcePage>(`/api/sources?${query}`)
  },
  setSourceEnabled: (key: string, enabled: boolean) =>
    request<Source>(`/api/sources/${key}`, {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    }),
  integrations: () =>
    request<{ integrations: Integration[] }>('/api/health/integrations').then(
      (body) => body.integrations,
    ),
  suggestions: (state = 'new', options: { writeFailed?: boolean } = {}) =>
    request<Suggestion[]>(
      `/api/suggestions?state=${state}${options.writeFailed ? '&write_failed=true' : ''}`,
    ),
  // Counted, not measured off the list: /api/suggestions pages at 100, so the
  // length of its first page is a floor and not a total.
  suggestionCounts: () => request<Record<string, number>>('/api/suggestions/counts'),
  addSuggestion: (id: number, status: ListStatus, download: boolean) =>
    request<{ ok: boolean; series_id: number; needs_review: boolean }>(
      `/api/suggestions/${id}/add`,
      { method: 'POST', body: JSON.stringify({ status, download }) },
    ),
  dismissSuggestion: (id: number) =>
    request<{ ok: boolean }>(`/api/suggestions/${id}/dismiss`, { method: 'POST' }),
  refreshDiscovery: () =>
    request<{ ok: boolean; queued: number }>('/api/discovery/refresh', { method: 'POST' }),
  // Unlike /api/suggestions this answers with an envelope, because 500 anime are
  // paged and a bare array could not carry the total.
  unmatched: (
    options: { hidden?: boolean; q?: string; limit?: number; offset?: number } = {},
  ) => {
    const query = new URLSearchParams({
      hidden: String(options.hidden ?? false),
      limit: String(options.limit ?? 50),
      offset: String(options.offset ?? 0),
    })
    // The route filters the whole list and counts what matched, so an empty
    // filter is simply left out rather than sent as one that matches all.
    if (options.q) query.set('q', options.q)
    return request<UnmatchedPage>(`/api/discovery/unmatched?${query}`)
  },
  unmatchedDetail: (id: number) =>
    request<UnmatchedDetail>(`/api/discovery/unmatched/${id}`),
  searchUnmatched: (id: number) =>
    request<UnmatchedSearch>(`/api/discovery/unmatched/${id}/search`, { method: 'POST' }),
  addUnmatched: (
    id: number,
    candidate: SearchCandidate,
    status: ListStatus,
    download: boolean,
  ) =>
    request<UnmatchedAdded>(`/api/discovery/unmatched/${id}/add`, {
      method: 'POST',
      // The route ignores unknown keys, so the candidate goes back as it arrived
      // rather than being re-assembled field by field and drifting from it.
      body: JSON.stringify({ ...candidate, status, download }),
    }),
  hideUnmatched: (id: number) =>
    request<HiddenResult>(`/api/discovery/unmatched/${id}/hide`, { method: 'POST' }),
  unhideUnmatched: (id: number) =>
    request<HiddenResult>(`/api/discovery/unmatched/${id}/hide`, { method: 'DELETE' }),
}
