// Queue a draft, cancel a task, delete a task. Cancel and delete ask first.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'

import { CANCELLABLE, taskKeys, type TaskDetail } from '@/entities/task'
import { api, call, errorText } from '@/shared/api'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
  Button,
  FormError,
} from '@/shared/ui'

type Action = 'queue' | 'cancel' | 'delete'

function run(action: Action, id: number) {
  const path = { params: { path: { task_id: id } } }
  if (action === 'queue') return call(api.POST('/api/v1/tasks/{task_id}/queue', path))
  if (action === 'cancel') return call(api.POST('/api/v1/tasks/{task_id}/cancel', path))
  return call(api.DELETE('/api/v1/tasks/{task_id}', path))
}

function useTaskAction(action: Action, task: TaskDetail, after?: () => void) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  return useMutation({
    mutationFn: () => run(action, task.id),
    onSuccess: async () => {
      after?.()
      if (action === 'delete') {
        queryClient.removeQueries({ queryKey: taskKeys.detail(task.id) })
        void navigate(`/workspaces/${task.workspace_id}`)
      } else {
        await queryClient.invalidateQueries({ queryKey: taskKeys.detail(task.id) })
      }
      await queryClient.invalidateQueries({ queryKey: taskKeys.list(task.workspace_id) })
    },
  })
}

/** Queue runs at once: a draft is easy to make again, nothing is lost. */
function QueueButton({ task }: { task: TaskDetail }) {
  const { t } = useTranslation()
  const mutation = useTaskAction('queue', task)
  return (
    <span className="flex items-center gap-2">
      <Button disabled={mutation.isPending} onClick={() => mutation.mutate()}>
        {t('taskActions.queue')}
      </Button>
      {mutation.isError && (
        <span role="alert" className="text-sm text-destructive">
          {errorText(mutation.error)}
        </span>
      )}
    </span>
  )
}

function ConfirmButton({ action, task }: { action: 'cancel' | 'delete'; task: TaskDetail }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const mutation = useTaskAction(action, task, () => setOpen(false))
  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (next) mutation.reset()
        setOpen(next)
      }}
    >
      <AlertDialogTrigger render={<Button variant="destructive">{t(`taskActions.${action}`)}</Button>} />
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t(`taskActions.${action}Title`, { title: task.title })}</AlertDialogTitle>
          <AlertDialogDescription>{t(`taskActions.${action}Text`)}</AlertDialogDescription>
        </AlertDialogHeader>
        <FormError error={mutation.isError ? errorText(mutation.error) : null} />
        <AlertDialogFooter>
          <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction variant="destructive" disabled={mutation.isPending} onClick={() => mutation.mutate()}>
            {t(`taskActions.${action}`)}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

/** The buttons for owner and editors (the caller checks the right). */
export function TaskActions({ task }: { task: TaskDetail }) {
  return (
    <>
      {task.status === 'draft' && <QueueButton task={task} />}
      {CANCELLABLE.includes(task.status) && <ConfirmButton action="cancel" task={task} />}
      {task.status !== 'running' && <ConfirmButton action="delete" task={task} />}
    </>
  )
}
