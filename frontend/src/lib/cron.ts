// A minimal cron builder/parser for the settings page's schedule control
// (off / daily at HH:MM / weekdays at HH:MM). The backend accepts any
// standard 5-field crontab string (CronTrigger.from_crontab); this frontend
// only ever needs to produce and re-read these two shapes.
export type ScheduleMode = 'off' | 'daily' | 'weekdays'

export function buildCron(mode: ScheduleMode, time: string): string | null {
  if (mode === 'off') return null
  const [h, m] = time.split(':').map(Number)
  return mode === 'weekdays' ? `${m} ${h} * * 1-5` : `${m} ${h} * * *`
}

export function parseCron(cron: string | null): { mode: ScheduleMode; time: string } {
  if (!cron) return { mode: 'off', time: '08:00' }
  const parts = cron.trim().split(/\s+/)
  if (parts.length < 5) return { mode: 'off', time: '08:00' }
  const [m, h, , , dow] = parts
  const hh = h.padStart(2, '0')
  const mm = m.padStart(2, '0')
  return { mode: dow === '1-5' ? 'weekdays' : 'daily', time: `${hh}:${mm}` }
}
