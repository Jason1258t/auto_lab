import { Monitor, Moon, Sun } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useTheme, type Theme } from '@/shared/lib/theme'
import { Button } from '@/shared/ui'

const NEXT: Record<Theme, Theme> = { system: 'light', light: 'dark', dark: 'system' }
const ICON = { light: Sun, dark: Moon, system: Monitor }

/** One button: system -> light -> dark -> system. */
export function ThemeToggle() {
  const { t } = useTranslation()
  const { theme, setTheme } = useTheme()
  const Icon = ICON[theme]
  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setTheme(NEXT[theme])}
      aria-label={t('theme.toggle', { current: t(`theme.${theme}`) })}
      title={t(`theme.${theme}`)}
    >
      <Icon />
    </Button>
  )
}
