// Create a workspace, or edit its name and description. Both open a dialog
// with the same two fields.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent, type ReactElement } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'

import { workspaceKeys, type Workspace } from '@/entities/workspace'
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
} from '@/shared/ui'

type Values = { name: string; description: string }

function WorkspaceDialog(props: {
  title: string
  submitLabel: string
  trigger: ReactElement
  initial: Values
  save: (values: Values) => Promise<unknown>
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [values, setValues] = useState(props.initial)
  const mutation = useMutation({ mutationFn: props.save, onSuccess: () => setOpen(false) })

  const onOpenChange = (next: boolean) => {
    if (next) {
      setValues(props.initial) // start from the saved values every time
      mutation.reset()
    }
    setOpen(next)
  }
  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    mutation.mutate(values)
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger render={props.trigger} />
      <DialogContent>
        <form onSubmit={onSubmit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{props.title}</DialogTitle>
          </DialogHeader>
          <FormField
            id="workspace-name"
            label={t('workspace.name')}
            value={values.name}
            onChange={(name) => setValues((v) => ({ ...v, name }))}
            maxLength={200}
          />
          <FormField
            id="workspace-description"
            label={t('workspace.description')}
            value={values.description}
            onChange={(description) => setValues((v) => ({ ...v, description }))}
            maxLength={5000}
            multiline
            required={false}
          />
          <FormError error={mutation.isError ? errorText(mutation.error) : null} />
          <DialogFooter>
            <Button type="submit" disabled={mutation.isPending}>
              {props.submitLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** An empty description means "no description" (the backend stores NULL). */
function body(values: Values) {
  return { name: values.name.trim(), description: values.description.trim() }
}

export function CreateWorkspaceButton() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const save = async (values: Values) => {
    const created = await call(api.POST('/api/v1/workspaces', { body: body(values) }))
    queryClient.setQueryData(workspaceKeys.detail(created.id), created) // no "Loading…" on the new page
    await queryClient.invalidateQueries({ queryKey: workspaceKeys.all })
    void navigate(`/workspaces/${created.id}`)
  }
  return (
    <WorkspaceDialog
      title={t('workspace.createTitle')}
      submitLabel={t('workspace.create')}
      trigger={<Button>{t('workspace.create')}</Button>}
      initial={{ name: '', description: '' }}
      save={save}
    />
  )
}

export function EditWorkspaceButton({ workspace }: { workspace: Workspace }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const save = async (values: Values) => {
    const updated = await call(
      api.PATCH('/api/v1/workspaces/{workspace_id}', {
        params: { path: { workspace_id: workspace.id } },
        body: body(values),
      }),
    )
    queryClient.setQueryData(workspaceKeys.detail(workspace.id), updated)
    await queryClient.invalidateQueries({ queryKey: workspaceKeys.all })
  }
  return (
    <WorkspaceDialog
      title={t('workspace.editTitle')}
      submitLabel={t('workspace.save')}
      trigger={<Button variant="outline">{t('workspace.edit')}</Button>}
      initial={{ name: workspace.name, description: workspace.description ?? '' }}
      save={save}
    />
  )
}
