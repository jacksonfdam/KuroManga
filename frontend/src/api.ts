export type SeriesState = 'mapped' | 'needs_review' | 'downloading' | 'failed'

export interface Series {
  id: number
  title: string
  slug: string
  cover_url: string | null
  source_site: string | null
  source_url: string | null
  providers: string[]
  downloaded: number
  known: number
  in_flight: number
  failed: number
  total_chapters: number | null
  auto_download: boolean
  state: SeriesState
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

export interface Job {
  id: number
  type: string
  state: string
  attempts: number
  max_attempts: number
  last_error: string | null
  series_title: string | null
  chapter_number: number | null
  chapter_title: string | null
  pct: number | null
  last_message: string | null
  created_at: string | null
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
  providers: Record<string, { connected: boolean; configured: boolean; account_name?: string }>
  sources: Record<string, SourceStatus>
  library_path: string
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

export type ListStatusValue = 'reading' | 'plan_to_read' | 'completed' | 'on_hold' | 'dropped'

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(detail || `${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

export const api = {
  series: (state?: string) =>
    request<Series[]>(`/api/series${state ? `?state=${state}` : ''}`),
  chapters: (id: number) => request<unknown[]>(`/api/series/${id}/chapters`),
  candidates: (id: number) => request<ReviewPayload>(`/api/series/${id}/candidates`),
  confirmMapping: (id: number, sourceUrl: string) =>
    request<{ ok: boolean }>(`/api/series/${id}/mapping`, {
      method: 'POST',
      body: JSON.stringify({ source_url: sourceUrl }),
    }),
  research: (id: number) =>
    request<{ ok: boolean }>(`/api/series/${id}/search`, { method: 'POST' }),
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
  jobs: (state?: string) => request<Job[]>(`/api/jobs${state ? `?state=${state}` : ''}`),
  jobCounts: () => request<Record<string, number>>('/api/jobs/counts'),
  jobEvents: (id: number) => request<JobEvent[]>(`/api/jobs/${id}/events`),
  retry: (id: number) => request<{ ok: boolean }>(`/api/jobs/${id}/retry`, { method: 'POST' }),
  sync: (provider: string) =>
    request<{ ok: boolean }>(`/api/sync/${provider}`, { method: 'POST' }),
  settings: () => request<SettingsPayload>('/api/settings'),
  saveSettings: (values: Record<string, string>) =>
    request<SettingsPayload>('/api/settings', {
      method: 'PUT',
      body: JSON.stringify({ values }),
    }),
  authStart: (provider: string) => request<{ url: string }>(`/api/auth/${provider}/start`),
  disconnect: (provider: string) =>
    request<{ ok: boolean }>(`/api/auth/${provider}`, { method: 'DELETE' }),
  suggestions: (state = 'new') => request<Suggestion[]>(`/api/suggestions?state=${state}`),
  addSuggestion: (id: number, status: ListStatusValue, download: boolean) =>
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
  searchUnmatched: (id: number) =>
    request<UnmatchedSearch>(`/api/discovery/unmatched/${id}/search`, { method: 'POST' }),
  addUnmatched: (
    id: number,
    candidate: SearchCandidate,
    status: ListStatusValue,
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
