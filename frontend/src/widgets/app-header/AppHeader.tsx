import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { useSession } from '@/entities/session'
import { ThemeToggle } from '@/features/theme-toggle'
import { Button } from '@/shared/ui'

export function AppHeader() {
  const { t } = useTranslation()
  const { me, logout } = useSession()
  return (
    <header className="border-b border-border">
      <div className="mx-auto flex max-w-5xl items-center gap-4 px-4 py-3">
        <Link to="/" className="font-heading text-xl font-semibold">
          {t('app.name')}
        </Link>
        <nav className="flex-1">
          <Link to="/" className="text-sm text-muted-foreground hover:text-foreground">
            {t('nav.workspaces')}
          </Link>
        </nav>
        <span className="text-sm text-muted-foreground">{me?.display_name}</span>
        <ThemeToggle />
        <Button variant="outline" size="sm" onClick={() => void logout()}>
          {t('nav.logout')}
        </Button>
      </div>
    </header>
  )
}
