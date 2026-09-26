// m:ss for episode lengths and playback positions; "—" when unknown.
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return '—'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}
