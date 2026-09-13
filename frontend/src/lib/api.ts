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
  sources: Record<string, { authenticated: boolean; username: string | null }>
  library_path: string
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
  integrations: () =>
    request<{ integrations: { name: string; state: string; detail: string | null }[] }>(
      '/api/health/integrations',
    ).then((body) => body.integrations),
}
