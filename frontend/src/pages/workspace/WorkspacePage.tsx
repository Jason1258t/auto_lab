// One workspace: name, description, facts and the actions the user may
// use. People inside also see tabs: tasks, files, members, activity.
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams, useSearchParams } from 'react-router'

import { useSession } from '@/entities/session'

import { useWorkspace, useWorkspaceFacts, workspaceRights, type Workspace } from '@/entities/workspace'
import { WorkspaceActions } from '@/features/workspace-actions'
import { EditWorkspaceButton } from '@/features/workspace-form'
import { ApiError, errorText } from '@/shared/api'
import { Alert, AlertDescription, FormError, Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/ui'
import { WorkspaceActivity } from '@/widgets/workspace-activity'
import { WorkspaceFiles } from '@/widgets/workspace-files'
import { WorkspaceMembers } from '@/widgets/workspace-members'
import { WorkspaceTasks } from '@/widgets/workspace-tasks'
import { WorkspaceWorks } from '@/widgets/workspace-works'

function WorkspaceHeader({ workspace }: { workspace: Workspace }) {
  const { t } = useTranslation()
  const facts = useWorkspaceFacts(workspace)
  return (
    <header className="grid gap-3">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="grid gap-1">
          <h1 className="font-heading text-3xl font-semibold">{workspace.name}</h1>
          <p className="text-sm text-muted-foreground">{facts}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {workspaceRights(workspace).edit && <EditWorkspaceButton workspace={workspace} />}
          <WorkspaceActions workspace={workspace} />
        </div>
      </div>
      {workspace.description && <p className="whitespace-pre-line">{workspace.description}</p>}
      {workspace.archived_at && (
        <Alert>
          <AlertDescription>{t('workspace.archivedNote')}</AlertDescription>
        </Alert>
      )}
    </header>
  )
}

type Tab = 'tasks' | 'works' | 'files' | 'members' | 'activity'

/** The tabs for people inside the workspace (admins too). Visitors of a
 *  public workspace see only its accepted works. */
function WorkspaceTabs({ workspace }: { workspace: Workspace }) {
  const { t } = useTranslation()
  const { me } = useSession()
  const [params, setParams] = useSearchParams()
  const rights = workspaceRights(workspace)
  const admin = Boolean(me?.is_admin)
  if (!rights.seeInside && !admin) {
    return workspace.visibility === 'public' ? <WorkspaceWorks workspace={workspace} /> : null
  }

  const tabs: Tab[] = ['tasks', 'works', 'files', 'members']
  if (rights.readActivity || admin) tabs.push('activity')
  const tab = tabs.find((name) => name === params.get('tab')) ?? 'tasks'
  const panels: Record<Tab, ReactNode> = {
    tasks: <WorkspaceTasks workspace={workspace} />,
    works: <WorkspaceWorks workspace={workspace} />,
    files: <WorkspaceFiles workspace={workspace} />,
    members: <WorkspaceMembers workspace={workspace} />,
    activity: <WorkspaceActivity workspace={workspace} />,
  }
  return (
    <Tabs
      value={tab}
      onValueChange={(value) => setParams(value === 'tasks' ? {} : { tab: String(value) }, { replace: true })}
      className="gap-4"
    >
      <TabsList>
        {tabs.map((name) => (
          <TabsTrigger key={name} value={name}>
            {t(`workspace.tabs.${name}`)}
          </TabsTrigger>
        ))}
      </TabsList>
      {tabs.map((name) => (
        <TabsContent key={name} value={name}>
          {panels[name]}
        </TabsContent>
      ))}
    </Tabs>
  )
}

export function WorkspacePage() {
  const { t } = useTranslation()
  const id = Number(useParams().workspaceId)
  const workspace = useWorkspace(id)
  return (
    <section className="grid gap-6">
      <Link to="/" className="text-sm text-muted-foreground hover:text-foreground">
        ← {t('nav.workspaces')}
      </Link>
      {workspace.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
      {workspace.isError &&
        (workspace.error instanceof ApiError && workspace.error.status === 404 ? (
          <p className="text-muted-foreground">{t('workspace.notFound')}</p>
        ) : (
          <FormError error={errorText(workspace.error)} />
        ))}
      {workspace.data && (
        <>
          <WorkspaceHeader workspace={workspace.data} />
          <WorkspaceTabs workspace={workspace.data} />
        </>
      )}
    </section>
  )
}
