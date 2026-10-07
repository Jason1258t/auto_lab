// Create a task (a draft), or edit a draft. A draft runs only after
// "Queue" on the task page, so it can be checked first.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'

import { useModels, usePipelines } from '@/entities/catalog'
import { useMembers } from '@/entities/member'
import { useSession } from '@/entities/session'
import { taskKeys, type TaskDetail } from '@/entities/task'
import type { Workspace } from '@/entities/workspace'
import { api, call, errorText } from '@/shared/api'
import {
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  FormError,
  FormField,
  SelectField,
} from '@/shared/ui'

type Values = { title: string; input: string }

/** Title and task text, the error, and the submit button. The form is
 *  mounted only while the dialog is open, so it starts fresh each time. */
function TaskFormBody(props: {
  title: string
  submitLabel: string
  initial: Values
  save: (values: Values) => Promise<unknown>
  onDone: () => void
  extra?: ReactNode
  ready?: boolean
}) {
  const { t } = useTranslation()
  const [values, setValues] = useState(props.initial)
  const mutation = useMutation({ mutationFn: props.save, onSuccess: props.onDone })
  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    mutation.mutate({ title: values.title.trim(), input: values.input.trim() })
  }
  return (
    <form onSubmit={onSubmit} className="grid gap-4">
      <DialogHeader>
        <DialogTitle>{props.title}</DialogTitle>
      </DialogHeader>
      <FormField
        id="task-title"
        label={t('task.titleField')}
        value={values.title}
        onChange={(title) => setValues((v) => ({ ...v, title }))}
        maxLength={300}
      />
      <FormField
        id="task-input"
        label={t('task.input')}
        hint={t('task.inputHint')}
        value={values.input}
        onChange={(input) => setValues((v) => ({ ...v, input }))}
        maxLength={20000}
        multiline
      />
      {props.extra}
      <FormError error={mutation.isError ? errorText(mutation.error) : null} />
      <DialogFooter>
        <Button type="submit" disabled={mutation.isPending || props.ready === false}>
          {props.submitLabel}
        </Button>
      </DialogFooter>
    </form>
  )
}

function CreateTaskForm({ workspace, onDone }: { workspace: Workspace; onDone: () => void }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { me } = useSession()
  const pipelines = usePipelines()
  const models = useModels()
  const members = useMembers(workspace.id)

  // Only pipelines the worker has synced (they have a version) and
  // models an admin marked available.
  const pipelineOptions = (pipelines.data ?? [])
    .filter((p) => p.version_id !== null)
    .map((p) => ({ value: String(p.id), label: `${p.name} ${p.version_name ?? ''}`.trim() }))
  const modelOptions = (models.data ?? [])
    .filter((m) => m.available)
    .map((m) => ({ value: String(m.id), label: m.name }))
  // '' = the backend default: the creator reviews.
  const reviewerOptions = [
    { value: '', label: t('task.reviewerMe') },
    ...(workspace.owner_id !== null && workspace.owner_id !== me?.id
      ? [{ value: String(workspace.owner_id), label: workspace.owner_display_name ?? '' }]
      : []),
    ...(members.data ?? [])
      .filter((m) => m.user_id !== me?.id)
      .map((m) => ({ value: String(m.user_id), label: m.display_name })),
  ]
  const [pipelineId, setPipelineId] = useState('')
  const [modelId, setModelId] = useState('')
  const [reviewerId, setReviewerId] = useState('')
  const pipeline = pipelineId || pipelineOptions[0]?.value || ''
  const model = modelId || modelOptions[0]?.value || ''

  const save = async (values: Values) => {
    const created = await call(
      api.POST('/api/v1/workspaces/{workspace_id}/tasks', {
        params: { path: { workspace_id: workspace.id } },
        body: {
          ...values,
          pipeline_id: Number(pipeline),
          model_id: Number(model),
          ...(reviewerId ? { reviewer_id: Number(reviewerId) } : {}),
        },
      }),
    )
    await queryClient.invalidateQueries({ queryKey: taskKeys.list(workspace.id) })
    void navigate(`/tasks/${created.id}`)
  }
  const loading = pipelines.isPending || models.isPending
  const missing = !pipelineOptions.length ? 'task.noPipelines' : !modelOptions.length ? 'task.noModels' : null
  return (
    <TaskFormBody
      title={t('task.createTitle')}
      submitLabel={t('task.create')}
      initial={{ title: '', input: '' }}
      save={save}
      onDone={onDone}
      ready={!loading && !missing}
      extra={
        <>
          <SelectField id="task-pipeline" label={t('task.pipeline')} value={pipeline} onChange={setPipelineId} options={pipelineOptions} />
          <SelectField id="task-model" label={t('task.model')} value={model} onChange={setModelId} options={modelOptions} />
          <SelectField id="task-reviewer" label={t('task.reviewer')} value={reviewerId} onChange={setReviewerId} options={reviewerOptions} />
          {!loading && missing && <FormError error={t(missing)} />}
        </>
      }
    />
  )
}

export function CreateTaskButton({ workspace }: { workspace: Workspace }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button>{t('task.create')}</Button>} />
      <DialogContent className="sm:max-w-lg">
        {open && <CreateTaskForm workspace={workspace} onDone={() => setOpen(false)} />}
      </DialogContent>
    </Dialog>
  )
}

export function EditTaskButton({ task }: { task: TaskDetail }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const save = async (values: Values) => {
    await call(api.PATCH('/api/v1/tasks/{task_id}', { params: { path: { task_id: task.id } }, body: values }))
    await queryClient.invalidateQueries({ queryKey: taskKeys.detail(task.id) })
    await queryClient.invalidateQueries({ queryKey: taskKeys.list(task.workspace_id) })
  }
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="outline">{t('workspace.edit')}</Button>} />
      <DialogContent className="sm:max-w-lg">
        {open && (
          <TaskFormBody
            title={t('task.editTitle')}
            submitLabel={t('workspace.save')}
            initial={{ title: task.title, input: task.input }}
            save={save}
            onDone={() => setOpen(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}
