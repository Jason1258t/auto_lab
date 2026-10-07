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
