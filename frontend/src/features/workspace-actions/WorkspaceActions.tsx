// Archive, unarchive, make public, take, leave, delete. Each one asks
// first, because most of them cannot be undone.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'

import { workspaceKeys, workspaceRights, type Workspace } from '@/entities/workspace'
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

type Action = 'archive' | 'unarchive' | 'makePublic' | 'take' | 'leave' | 'delete'

const ORDER: Action[] = ['take', 'makePublic', 'archive', 'unarchive', 'leave', 'delete']
const DANGER = new Set<Action>(['archive', 'leave', 'delete'])

function run(action: Action, id: number) {
  const path = { params: { path: { workspace_id: id } } }
  switch (action) {
    case 'archive':
      return call(api.POST('/api/v1/workspaces/{workspace_id}/archive', path))
    case 'unarchive':
      return call(api.POST('/api/v1/workspaces/{workspace_id}/unarchive', path))
    case 'makePublic':
      return call(api.POST('/api/v1/workspaces/{workspace_id}/make-public', path))
    case 'take':
      return call(api.POST('/api/v1/workspaces/{workspace_id}/take', path))
    case 'leave':
      return call(api.POST('/api/v1/workspaces/{workspace_id}/leave', path))
    case 'delete':
      return call(api.DELETE('/api/v1/workspaces/{workspace_id}', path))
  }
}

function ConfirmAction({ action, workspace }: { action: Action; workspace: Workspace }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const mutation = useMutation({
    mutationFn: () => run(action, workspace.id),
    onSuccess: async () => {
      setOpen(false)
      // After leave or delete the page is gone for this user.
      const gone = action === 'leave' || action === 'delete'
      if (gone) {
        queryClient.removeQueries({ queryKey: workspaceKeys.detail(workspace.id) })
        void navigate('/')
      }
      await queryClient.invalidateQueries({ queryKey: workspaceKeys.all })
    },
  })
  const variant = DANGER.has(action) ? 'destructive' : 'outline'
  // Archiving a public workspace also removes its owner: say so.
  const textKey = action === 'archive' && workspace.visibility === 'public' ? 'archivePublicText' : `${action}Text`
  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (next) mutation.reset()
        setOpen(next)
      }}
    >
      <AlertDialogTrigger render={<Button variant={variant}>{t(`workspaceActions.${action}`)}</Button>} />
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t(`workspaceActions.${action}Title`, { name: workspace.name })}</AlertDialogTitle>
          <AlertDialogDescription>{t(`workspaceActions.${textKey}`)}</AlertDialogDescription>
        </AlertDialogHeader>
        <FormError error={mutation.isError ? errorText(mutation.error) : null} />
        <AlertDialogFooter>
          <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction
            variant={DANGER.has(action) ? 'destructive' : 'default'}
            disabled={mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {t(`workspaceActions.${action}`)}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

/** The buttons the current user may use; none if there are none. */
export function WorkspaceActions({ workspace }: { workspace: Workspace }) {
  const rights = workspaceRights(workspace)
  return (
    <>
      {ORDER.filter((action) => rights[action]).map((action) => (
        <ConfirmAction key={action} action={action} workspace={workspace} />
      ))}
    </>
  )
}
