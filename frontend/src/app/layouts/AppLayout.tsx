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
  if (status === 'loading') return <p className="p-8 text-muted-foreground">{t('common.loading')}</p>
  if (status === 'signed_out') return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  return children
}

/** Pages anyone may open (public workspaces and works). Waits for the
 *  silent refresh, so a logged-in user still gets their own view. */
export function WaitForSession({ children }: { children: ReactNode }) {
  const { t } = useTranslation()
  const { status } = useSession()
  if (status === 'loading') return <p className="p-8 text-muted-foreground">{t('common.loading')}</p>
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
