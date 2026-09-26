// Hand-written to match backend/app/api/schemas.py and backend/app/schemas.py
// exactly (docs/phases/06-frontend.md "cut first": generated OpenAPI types).
// Keep this file in sync by hand if those schemas change.

export type Depth = 'headlines' | 'deep'

export interface Topic {
  name: string
  description: string
  include: string[]
  exclude: string[]
  depth: Depth
}

export interface InterestProfile {
  topics: Topic[]
  avoid: string[]
}

export interface TokenResponse {
  access_token: string
  token_type: 'bearer'
}

export interface MeResponse {
  id: number
  email: string
  is_admin: boolean
  has_profile: boolean
}

export interface QuestionOut {
  key: string
  question: string
}

export interface HostOut {
  name: string
  voice_id: string
}

export interface HostIn {
  name: string
  voice_id: string
}

export type Tone = 'conversational' | 'focused' | 'playful'

export interface PreferencesOut {
  interest_profile: InterestProfile
  target_minutes: number
  tone: Tone | null
  host_a: HostOut
  host_b: HostOut
  schedule_cron: string | null
  timezone: string
  next_run_at: string | null
}

export interface PreferencesUpdate {
  interest_profile?: InterestProfile
  target_minutes?: number
  tone?: Tone
  host_a?: HostIn
  host_b?: HostIn
  schedule_cron?: string | null
  timezone?: string
}

export interface LengthOption {
  minutes: number
  stories: number
}

export interface VoiceOut {
  id: string
  name: string
  label: string
  preview_url: string | null
}

export interface EpisodeGenerateRequest {
  focus_request?: string
  target_minutes?: number
}

export interface EpisodeCreated {
  id: number
  status: string
  target_minutes: number
}

// The pipeline's own status machine (docs/ARCHITECTURE.md §5); EpisodeListItem
// / EpisodeDetail.status is one of these while running, "ready" when done.
export const STAGE_ORDER = [
  'pending',
  'planning',
  'fetching',
  'ranking',
  'extracting',
  'scripting',
  'voicing',
  'assembling',
] as const

export type Stage = (typeof STAGE_ORDER)[number]
export type EpisodeStatus = Stage | 'ready' | 'failed'

export function isTerminal(status: string): boolean {
  return status === 'ready' || status === 'failed'
}

export interface EpisodeListItem {
  id: number
  status: string
  failed_stage: string | null
  error: string | null
  trigger: string
  focus_request: string | null
  title: string | null
  target_minutes: number
  duration_s: number | null
  created_at: string
}

export interface TranscriptTurn {
  speaker: string
  text: string
}

export interface SourceArticle {
  title: string | null
  outlet: string | null
  url: string
}

export interface TranscriptSection {
  kind: 'intro' | 'story' | 'outro'
  story_id: string | null
  heading: string | null
  topic: string | null
  turns: TranscriptTurn[]
  sources: SourceArticle[]
}

export interface StepSummary {
  stage: string
  status: string
  provider: string
  model: string | null
  units_in: number | null
  units_out: number | null
  cost_usd: number
  cost_is_estimate: boolean
  latency_ms: number | null
}

export interface EpisodeDetail {
  id: number
  status: string
  failed_stage: string | null
  error: string | null
  trigger: string
  focus_request: string | null
  title: string | null
  summary: string | null
  target_minutes: number
  duration_s: number | null
  created_at: string
  ready_at: string | null
  audio_url: string | null
  my_rating: 1 | -1 | null
  sections: TranscriptSection[]
  steps: StepSummary[]
}

export type ClientEventType = 'play_started' | 'play_progress' | 'play_completed' | 'episode_rated'

export interface EventCreate {
  type: ClientEventType
  episode_id: number
  payload?: Record<string, unknown>
}
