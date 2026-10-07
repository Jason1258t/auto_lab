// First screen after login. The full workspace pages come in the next PR.
import { useTranslation } from 'react-i18next'

import { useWorkspaces, WorkspaceCard } from '@/entities/workspace'
import { errorText } from '@/shared/api'
import { Alert, AlertDescription } from '@/shared/ui'

export function WorkspacesPage() {
  const { t } = useTranslation()
  const workspaces = useWorkspaces('mine')
  return (
    <section className="grid gap-6">
      <h1 className="font-heading text-3xl font-semibold">{t('workspaces.title')}</h1>
      {workspaces.isPending && <p className="text-muted-foreground">{t('auth.loading')}</p>}
      {workspaces.isError && (
        <Alert variant="destructive">
          <AlertDescription>{errorText(workspaces.error)}</AlertDescription>
        </Alert>
      )}
      {workspaces.data?.length === 0 && <p className="text-muted-foreground">{t('workspaces.empty')}</p>}
      <ul className="grid gap-3 sm:grid-cols-2">
        {workspaces.data?.map((w) => (
          <li key={w.id}>
            <WorkspaceCard workspace={w} />
          </li>
        ))}
      </ul>
    </section>
  )
}
