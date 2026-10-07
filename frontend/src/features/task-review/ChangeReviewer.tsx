// Owner and editors can give the review to another person in the
// workspace, until the task is done or cancelled.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { taskKeys, type TaskDetail } from '@/entities/task'
import { api, call, errorText } from '@/shared/api'
import { NativeSelect, NativeSelectOption } from '@/shared/ui'

export function ChangeReviewer({ task, people }: { task: TaskDetail; people: { id: number; name: string }[] }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: (reviewerId: number) =>
      call(
        api.PATCH('/api/v1/tasks/{task_id}', {
          params: { path: { task_id: task.id } },
          body: { reviewer_id: reviewerId },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: taskKeys.detail(task.id) }),
  })
  return (
    <span className="flex flex-wrap items-center gap-2 text-sm">
      <label htmlFor="task-reviewer-change" className="text-muted-foreground">
        {t('task.reviewer')}
      </label>
      <NativeSelect
        id="task-reviewer-change"
        size="sm"
        value={String(task.reviewer_id ?? '')}
        disabled={mutation.isPending}
        onChange={(e) => mutation.mutate(Number(e.target.value))}
      >
        {task.reviewer_id === null && <NativeSelectOption value="">—</NativeSelectOption>}
        {people.map((person) => (
          <NativeSelectOption key={person.id} value={String(person.id)}>
            {person.name}
          </NativeSelectOption>
        ))}
      </NativeSelect>
      {mutation.isError && (
        <span role="alert" className="text-destructive">
          {errorText(mutation.error)}
        </span>
      )}
    </span>
  )
}
