import type {
  AdminMetrics,
  EpisodeCreated,
  EpisodeDetail,
  EpisodeGenerateRequest,
  EpisodeListItem,
  EventCreate,
  InterestProfile,
  LengthOption,
  MeResponse,
  PreferencesOut,
  PreferencesUpdate,
  QuestionOut,
  TokenResponse,
  VoiceOut,
} from './types'

export const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

const TOKEN_KEY = 'podcast_token'

let token: string | null = localStorage.getItem(TOKEN_KEY)
let onUnauthorized: (() => void) | null = null

export function setToken(next: string | null) {
  token = next
  if (next) localStorage.setItem(TOKEN_KEY, next)
  else localStorage.removeItem(TOKEN_KEY)
}

export function getToken(): string | null {
  return token
}

export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn
}

// A resource path returned by the API (audio_url, preview_url) that a plain
// <audio>/<img> tag needs as an absolute URL, since those elements can't go
// through request() to get the base URL or an Authorization header.
export function absoluteUrl(path: string): string {
  return `${BASE_URL}${path}`
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (!(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers })

  if (res.status === 401) {
    setToken(null)
    onUnauthorized?.()
    throw new ApiError(401, 'unauthorized')
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = (await res.json()) as { detail?: unknown }
      if (body.detail) detail = JSON.stringify(body.detail)
    } catch {
      // no JSON body
    }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export const api = {
  login: (email: string, password: string) =>
    request<TokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  signup: (email: string, password: string) =>
    request<TokenResponse>('/auth/signup', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<MeResponse>('/me'),

  profileQuestions: () => request<QuestionOut[]>('/profile/questions'),
  extractProfile: (answers: Record<string, string>) =>
    request<InterestProfile>('/profile/extract', {
      method: 'POST',
      body: JSON.stringify({ answers }),
    }),

  getPreferences: () => request<PreferencesOut>('/preferences'),
  updatePreferences: (body: PreferencesUpdate) =>
    request<PreferencesOut>('/preferences', { method: 'PUT', body: JSON.stringify(body) }),
  lengthOptions: () => request<LengthOption[]>('/preferences/length-options'),

  voices: () => request<VoiceOut[]>('/voices'),

  listEpisodes: () => request<EpisodeListItem[]>('/episodes'),
  getEpisode: (id: number) => request<EpisodeDetail>(`/episodes/${id}`),
  generateEpisode: (body: EpisodeGenerateRequest) =>
    request<EpisodeCreated>('/episodes/generate', { method: 'POST', body: JSON.stringify(body) }),
  retryEpisode: (id: number) =>
    request<EpisodeCreated>(`/episodes/${id}/retry`, { method: 'POST' }),

  // keepalive lets the last play_progress survive the tab being closed.
  sendEvent: (body: EventCreate) =>
    request<{ id: number }>('/events', { method: 'POST', body: JSON.stringify(body), keepalive: true }),

  adminMetrics: (params: { from: string; to: string; includeSynthetic: boolean }) =>
    request<AdminMetrics>(
      `/admin/metrics?${new URLSearchParams({
        from: params.from,
        to: params.to,
        include_synthetic: String(params.includeSynthetic),
      })}`,
    ),
}
