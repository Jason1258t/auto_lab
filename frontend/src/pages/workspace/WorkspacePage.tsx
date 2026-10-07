// One workspace: name, description, facts and the actions the user may
// use, and the members. Files, tasks and activity come in the next PR.
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'

import { useWorkspace, useWorkspaceFacts, workspaceRights, type Workspace } from '@/entities/workspace'
import { WorkspaceActions } from '@/features/workspace-actions'
import { EditWorkspaceButton } from '@/features/workspace-form'
import { ApiError, errorText } from '@/shared/api'
import { Alert, AlertDescription, FormError } from '@/shared/ui'
import { WorkspaceMembers } from '@/widgets/workspace-members'

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
          <WorkspaceMembers workspace={workspace.data} />
        </>
      )}
    </section>
  )
}
