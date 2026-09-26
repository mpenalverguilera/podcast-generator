// Chart colors for the admin dashboard, taken from the dataviz skill's
// validated default categorical palette (light mode only -- this app has no
// dark mode). Colors are assigned by entity and fixed forever: a provider or
// series keeps its slot even when a date-range/toggle change removes other
// series from the chart (never repaint the survivors).
export const SERIES = {
  blue: '#2a78d6',
  orange: '#eb6834',
  aqua: '#1baf7a',
  yellow: '#eda100',
  gray: '#b3b2ab', // fallback "Other" bucket for anything unmapped
} as const

export const STATUS_CRITICAL = '#d03b3b'

export const CHART_GRID = '#e1e0d9'
export const CHART_AXIS = '#898781'

const PROVIDER_COLORS: Record<string, string> = {
  exa: SERIES.blue,
  openai: SERIES.orange,
  vercel_gateway: SERIES.aqua,
  elevenlabs: SERIES.yellow,
}

const PROVIDER_LABELS: Record<string, string> = {
  exa: 'Exa',
  openai: 'OpenAI',
  vercel_gateway: 'Jev',
  elevenlabs: 'ElevenLabs',
}

export function providerColor(provider: string): string {
  return PROVIDER_COLORS[provider] ?? SERIES.gray
}

export function providerLabel(provider: string): string {
  return PROVIDER_LABELS[provider] ?? provider
}

// Fixed rendering order (roughly the pipeline order the providers are called
// in) so a stacked bar's segment order never reshuffles across date ranges.
const PROVIDER_ORDER = ['exa', 'openai', 'vercel_gateway', 'elevenlabs']

export function orderProviders(providers: Iterable<string>): string[] {
  const set = new Set(providers)
  const known = PROVIDER_ORDER.filter((p) => set.has(p))
  const unknown = [...set].filter((p) => !PROVIDER_ORDER.includes(p)).sort()
  return [...known, ...unknown]
}
