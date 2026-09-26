// m:ss for episode lengths and playback positions; "—" when unknown.
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return '—'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

export function formatPercent(value: number | null | undefined, digits = 0): string {
  if (value == null) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

export function formatCurrency(value: number | null | undefined, digits = 2): string {
  if (value == null) return '—'
  return `$${value.toFixed(digits)}`
}

// Compact display for KPI tiles: 1284 -> "1.3K".
export function formatCompact(value: number | null | undefined): string {
  if (value == null) return '—'
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
}
