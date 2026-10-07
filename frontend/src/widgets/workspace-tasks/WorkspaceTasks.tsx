// The task list of a workspace, and "New task" for owner and editors.
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { TaskStatusBadge, useTasks } from '@/entities/task'
import { workspaceRights, type Workspace } from '@/entities/workspace'
import { CreateTaskButton } from '@/features/task-form'
import { errorText } from '@/shared/api'
import { formatDateTime } from '@/shared/lib/format'
import { Card, CardContent, CardHeader, CardTitle, FormError } from '@/shared/ui'

export function WorkspaceTasks({ workspace }: { workspace: Workspace }) {
  const { t } = useTranslation()
  const tasks = useTasks(workspace.id)
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('tasks.title')}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        {workspaceRights(workspace).editTasks && (
          <div>
            <CreateTaskButton workspace={workspace} />
          </div>
        )}
        {tasks.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
        {tasks.isError && <FormError error={errorText(tasks.error)} />}
        {tasks.data?.length === 0 && <p className="text-muted-foreground">{t('tasks.empty')}</p>}
        <ul className="divide-y divide-border">
          {tasks.data?.map((task) => (
            <li key={task.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
              <div className="grid min-w-0">
                <Link to={`/tasks/${task.id}`} className="truncate font-medium hover:underline">
                  {task.title}
                </Link>
                <span className="text-sm text-muted-foreground">
                  {task.pipeline_name} · {formatDateTime(task.created_at)}
                </span>
              </div>
              <TaskStatusBadge status={task.status} />
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}
