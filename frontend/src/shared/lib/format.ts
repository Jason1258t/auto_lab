import i18n from '@/shared/i18n'

/** "7 Oct 2026, 13:40" in the current language. */
export function formatDateTime(iso: string): string {
  return new Intl.DateTimeFormat(i18n.language, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(iso),
  )
}

/** "1.2 MB". Uses 1000, like most file managers. */
export function formatBytes(bytes: number): string {
  const units = ['B', 'kB', 'MB', 'GB']
  let value = bytes
  let unit = 0
  while (value >= 1000 && unit < units.length - 1) {
    value /= 1000
    unit += 1
  }
  const digits = unit === 0 || value >= 10 ? 0 : 1
  return `${new Intl.NumberFormat(i18n.language, { maximumFractionDigits: digits }).format(value)} ${units[unit]}`
}

/** "4.2 s", "42 s", "30 min", "12 min 5 s", "1 h 23 min". Long steps run
 * for minutes or hours, so plain seconds are hard to read. */
export function formatDuration(seconds: number): string {
  const t = i18n.t.bind(i18n)
  if (seconds < 10 && !Number.isInteger(seconds)) {
    return t('duration.seconds', { n: new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 1 }).format(seconds) })
  }
  const total = Math.round(seconds)
  if (total < 60) return t('duration.seconds', { n: total })
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const rest = total % 60
  if (hours > 0) {
    return minutes > 0 ? t('duration.hoursMinutes', { h: hours, m: minutes }) : t('duration.hours', { h: hours })
  }
  return rest > 0 ? t('duration.minutesSeconds', { m: minutes, s: rest }) : t('duration.minutes', { m: minutes })
}
