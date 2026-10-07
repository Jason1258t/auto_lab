import { useTranslation } from 'react-i18next'
import { Link, useLocation } from 'react-router'

import { useSession } from '@/entities/session'
import { ThemeToggle } from '@/features/theme-toggle'
import { Button, buttonVariants } from '@/shared/ui'

export function AppHeader() {
  const { t } = useTranslation()
  const { me, logout } = useSession()
  const location = useLocation()
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
        {me && <span className="text-sm text-muted-foreground">{me.display_name}</span>}
        <ThemeToggle />
        {me ? (
          <Button variant="outline" size="sm" onClick={() => void logout()}>
            {t('nav.logout')}
          </Button>
        ) : (
          <Link to="/login" state={{ from: location.pathname }} className={buttonVariants({ variant: 'outline', size: 'sm' })}>
            {t('auth.login')}
          </Link>
        )}
      </div>
    </header>
  )
}
