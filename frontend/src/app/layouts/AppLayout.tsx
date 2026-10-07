import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate, Outlet, useLocation } from 'react-router'

import { useSession } from '@/entities/session'
import { AppHeader } from '@/widgets/app-header'

/** Pages behind login. Waits for the silent refresh before deciding. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { t } = useTranslation()
  const { status } = useSession()
  const location = useLocation()
  if (status === 'loading') return <p className="p-8 text-muted-foreground">{t('auth.loading')}</p>
  if (status === 'signed_out') return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return children
}

export function AppLayout() {
  return (
    <div className="min-h-svh bg-background">
      <AppHeader />
      <main className="mx-auto max-w-5xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  )
}
