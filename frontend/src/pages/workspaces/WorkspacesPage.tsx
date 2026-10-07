// First screen after login: my workspaces, public ones, and free ones
// (public, archived, no owner: anyone can take them).
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router'

import { useWorkspaces, WorkspaceCard, type WorkspaceScope } from '@/entities/workspace'
import { CreateWorkspaceButton } from '@/features/workspace-form'
import { errorText } from '@/shared/api'
import { FormError, Tabs, TabsList, TabsTrigger } from '@/shared/ui'

const SCOPES: WorkspaceScope[] = ['mine', 'public', 'free']

function WorkspaceList({ scope }: { scope: WorkspaceScope }) {
  const { t } = useTranslation()
  const workspaces = useWorkspaces(scope)
  if (workspaces.isPending) return <p className="text-muted-foreground">{t('common.loading')}</p>
  if (workspaces.isError) return <FormError error={errorText(workspaces.error)} />
  if (workspaces.data.length === 0) {
    return <p className="text-muted-foreground">{t(`workspaces.empty.${scope}`)}</p>
  }
  return (
    <ul className="grid gap-3 sm:grid-cols-2">
      {workspaces.data.map((w) => (
        <li key={w.id}>
          <Link to={`/workspaces/${w.id}`} className="block h-full rounded-xl">
            <WorkspaceCard workspace={w} />
          </Link>
        </li>
      ))}
    </ul>
  )
}

export function WorkspacesPage() {
  const { t } = useTranslation()
  // The tab is in the address, so "back" returns to the same tab.
  const [params, setParams] = useSearchParams()
  const scope = SCOPES.find((s) => s === params.get('scope')) ?? 'mine'
  return (
    <section className="grid gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="font-heading text-3xl font-semibold">{t('workspaces.title')}</h1>
        <CreateWorkspaceButton />
      </div>
      <Tabs
        value={scope}
        onValueChange={(value) => setParams(value === 'mine' ? {} : { scope: String(value) }, { replace: true })}
      >
        <TabsList>
          {SCOPES.map((s) => (
            <TabsTrigger key={s} value={s}>
              {t(`workspaces.tabs.${s}`)}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      <WorkspaceList scope={scope} />
    </section>
  )
}
