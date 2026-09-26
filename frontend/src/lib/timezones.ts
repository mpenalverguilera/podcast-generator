const COMMON_TIMEZONES = [
  'UTC',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Sao_Paulo',
  'Europe/London',
  'Europe/Madrid',
  'Europe/Berlin',
  'Asia/Kolkata',
  'Asia/Tokyo',
  'Australia/Sydney',
]

export function timezoneOptions(current: string): string[] {
  const browser = Intl.DateTimeFormat().resolvedOptions().timeZone
  return Array.from(new Set([current, browser, ...COMMON_TIMEZONES])).sort()
}
