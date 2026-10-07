// The task list of a workspace. Creating a task and the task page come
// with screen 3.
import { useTranslation } from 'react-i18next'

import { TaskStatusBadge, useTasks } from '@/entities/task'
import type { Workspace } from '@/entities/workspace'
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
        {tasks.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
        {tasks.isError && <FormError error={errorText(tasks.error)} />}
        {tasks.data?.length === 0 && <p className="text-muted-foreground">{t('tasks.empty')}</p>}
        <ul className="divide-y divide-border">
          {tasks.data?.map((task) => (
            <li key={task.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
              <div className="grid min-w-0">
                <span className="truncate font-medium">{task.title}</span>
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
