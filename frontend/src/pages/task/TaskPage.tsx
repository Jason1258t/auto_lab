// One task: what was asked, the steps (live while the worker runs), and
// the actions for owner and editors. LLM calls and review come next.
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'

import { ACTIVE, stepRows, TaskStatusBadge, TaskSteps, useTask, type TaskDetail } from '@/entities/task'
import { useWorkspace, workspaceRights } from '@/entities/workspace'
import { TaskActions } from '@/features/task-actions'
import { EditTaskButton } from '@/features/task-form'
import { ApiError, errorText } from '@/shared/api'
import { formatDateTime } from '@/shared/lib/format'
import { Alert, AlertDescription, Card, CardContent, CardHeader, CardTitle, FormError } from '@/shared/ui'

function TaskView({ task }: { task: TaskDetail }) {
  const { t } = useTranslation()
  const workspace = useWorkspace(task.workspace_id)
  const canEdit = workspace.data ? workspaceRights(workspace.data).editTasks : false
  const live = ACTIVE.includes(task.status)
  return (
    <>
      <Link to={`/workspaces/${task.workspace_id}`} className="text-sm text-muted-foreground hover:text-foreground">
        ← {workspace.data?.name ?? t('nav.workspaces')}
      </Link>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="grid gap-1">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="font-heading text-3xl font-semibold">{task.title}</h1>
            <TaskStatusBadge status={task.status} />
          </div>
          <p className="text-sm text-muted-foreground">
            {task.pipeline_name} {task.pipeline_version} · {formatDateTime(task.created_at)}
          </p>
        </div>
        {canEdit && (
          <div className="flex flex-wrap gap-2">
            {task.status === 'draft' && <EditTaskButton task={task} />}
            <TaskActions task={task} />
          </div>
        )}
      </header>
      {task.status === 'draft' && (
        <Alert>
          <AlertDescription>{t('task.draftNote')}</AlertDescription>
        </Alert>
      )}
      {task.status === 'failed' && (
        <Alert variant="destructive">
          <AlertDescription>{t('task.failedNote')}</AlertDescription>
        </Alert>
      )}
      <Card>
        <CardHeader>
          <CardTitle>{t('task.input')}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="whitespace-pre-wrap">{task.input}</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {t('task.steps')}
            {live && <span className="text-xs font-normal text-muted-foreground">{t('task.live')}</span>}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {task.plan.length === 0 && task.steps.length === 0 ? (
            <p className="text-muted-foreground">{t('task.noPlan')}</p>
          ) : (
            <TaskSteps steps={stepRows(task)} />
          )}
        </CardContent>
      </Card>
    </>
  )
}

export function TaskPage() {
  const { t } = useTranslation()
  const id = Number(useParams().taskId)
  const task = useTask(id)
  return (
    <section className="grid gap-6">
      {task.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
      {task.isError &&
        (task.error instanceof ApiError && task.error.status === 404 ? (
          <p className="text-muted-foreground">{t('task.notFound')}</p>
        ) : (
          <FormError error={errorText(task.error)} />
        ))}
      {task.data && <TaskView task={task.data} />}
    </section>
  )
}
