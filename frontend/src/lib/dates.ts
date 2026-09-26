// Date-range presets for the admin dashboard (docs/phases/07-dashboard.md step 3).
export type RangePreset = 7 | 30 | 60

export const RANGE_PRESETS: RangePreset[] = [7, 30, 60]

// ISO date (YYYY-MM-DD), matching the backend's plain `date` columns and its
// [from 00:00 UTC, to+1day 00:00 UTC) window (app/metrics.py `_bounds`).
export function isoDateUTC(d: Date): string {
  return d.toISOString().slice(0, 10)
}

export function rangeForPreset(days: RangePreset, today: Date = new Date()): { from: string; to: string } {
  const to = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate()))
  const from = new Date(to)
  from.setUTCDate(from.getUTCDate() - (days - 1))
  return { from: isoDateUTC(from), to: isoDateUTC(to) }
}

// "Sep 12" axis ticks for an ISO date string.
export function formatShortDay(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  })
}
