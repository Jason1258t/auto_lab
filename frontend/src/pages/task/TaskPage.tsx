// One task: what was asked, the result and its review, the steps with
// their model calls (live while the worker runs), and the actions for
// owner and editors.
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'

import { CallList, useCalls } from '@/entities/call'
import { useMembers } from '@/entities/member'
import { ReviewList, useReviews } from '@/entities/review'
import { useSession } from '@/entities/session'
import { ACTIVE, POLL_MS, stepRows, TaskStatusBadge, TaskSteps, useTask, type TaskDetail } from '@/entities/task'
import { useWork, WorkView } from '@/entities/work'
import { useWorkspace, workspaceRights } from '@/entities/workspace'
import { TaskActions } from '@/features/task-actions'
import { EditTaskButton } from '@/features/task-form'
import { ChangeReviewer, ReviewForm } from '@/features/task-review'
import { ApiError, errorText } from '@/shared/api'
import { formatDateTime } from '@/shared/lib/format'
import { Alert, AlertDescription, Card, CardContent, CardHeader, CardTitle, FormError } from '@/shared/ui'

function TaskView({ task }: { task: TaskDetail }) {
  const { t } = useTranslation()
  const workspace = useWorkspace(task.workspace_id)
  const rights = workspace.data ? workspaceRights(workspace.data) : null
  const canEdit = rights?.editTasks ?? false
  const { me } = useSession()
  const members = useMembers(task.workspace_id)
  const reviews = useReviews(task.id)
  // The people who can be named on this page: the owner and the members.
  const people = [
    ...(workspace.data?.owner_id != null
      ? [{ id: workspace.data.owner_id, name: workspace.data.owner_display_name ?? '' }]
      : []),
    ...(members.data ?? []).map((m) => ({ id: m.user_id, name: m.display_name })),
  ]
  const nameOf = (id: number | null) =>
    people.find((p) => p.id === id)?.name ?? (id === null ? t('task.nobody') : t('task.userNumber', { id }))
  const canReview = task.status === 'in_review' && (me?.id === task.reviewer_id || (rights?.reviewAny ?? false))
  const reviewerChangeable = canEdit && task.status !== 'done' && task.status !== 'cancelled'
  const live = ACTIVE.includes(task.status)
  // Calls exist only after the worker has started the task.
  const calls = useCalls(task.id, live ? POLL_MS : false)
  // A work exists after the write step; asked for only from then on.
  const hasWork = task.status === 'in_review' || task.status === 'done' || task.steps.some((s) => s.kind === 'write' && s.status === 'done')
  const work = useWork(task.id, hasWork)
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
          {reviewerChangeable ? (
            <ChangeReviewer task={task} people={people} />
          ) : (
            <p className="text-sm text-muted-foreground">
              {t('task.reviewer')}: {nameOf(task.reviewer_id)}
            </p>
          )}
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
      {work.data && (
        <section className="grid gap-3">
          <h2 className="font-heading text-2xl font-semibold">{t('work.result')}</h2>
          <WorkView work={work.data} />
        </section>
      )}
      {(task.status === 'in_review' || (reviews.data?.length ?? 0) > 0) && (
        <Card>
          <CardHeader>
            <CardTitle>{t('review.title')}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4">
            {canReview && <ReviewForm task={task} />}
            {task.status === 'in_review' && !canReview && (
              <p className="text-muted-foreground">{t('review.waiting', { name: nameOf(task.reviewer_id) })}</p>
            )}
            {reviews.data && <ReviewList reviews={reviews.data} nameOf={nameOf} />}
          </CardContent>
        </Card>
      )}
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
            <TaskSteps
              steps={stepRows(task)}
              extra={(step) => <CallList calls={(calls.data ?? []).filter((c) => c.step_index === step.step_index)} />}
            />
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
