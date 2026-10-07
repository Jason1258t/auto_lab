// Grant or remove an extra role (a checkbox), and remove a person from
// the workspace (asks first).
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { memberKeys, type Member } from '@/entities/member'
import { type ExtraRole } from '@/entities/workspace'
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
  Checkbox,
  FormError,
} from '@/shared/ui'

type Props = { workspaceId: number; member: Member }

export function RoleCheckbox({ workspaceId, member, role }: Props & { role: ExtraRole }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const has = member.roles.includes(role)
  const mutation = useMutation({
    mutationFn: (grant: boolean) => {
      const options = { params: { path: { workspace_id: workspaceId, user_id: member.user_id, role } } }
      const path = '/api/v1/workspaces/{workspace_id}/members/{user_id}/roles/{role}' as const
      return call(grant ? api.PUT(path, options) : api.DELETE(path, options))
    },
    onSuccess: (updated) => {
      queryClient.setQueryData<Member[]>(memberKeys.list(workspaceId), (list) =>
        list?.map((m) => (m.user_id === updated.user_id ? updated : m)),
      )
    },
  })
  const id = `role-${member.user_id}-${role}`
  return (
    <span className="flex items-center gap-2">
      <Checkbox
        id={id}
        checked={has}
        disabled={mutation.isPending}
        onCheckedChange={(checked) => mutation.mutate(checked)}
        aria-invalid={mutation.isError || undefined}
      />
      <label htmlFor={id} className="text-sm">
        {t(`roles.${role}`)}
      </label>
      {mutation.isError && (
        <span role="alert" className="text-xs text-destructive">
          {errorText(mutation.error)}
        </span>
      )}
    </span>
  )
}

export function RemoveMemberButton({ workspaceId, member }: Props) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const mutation = useMutation({
    mutationFn: () =>
      call(
        api.DELETE('/api/v1/workspaces/{workspace_id}/members/{user_id}', {
          params: { path: { workspace_id: workspaceId, user_id: member.user_id } },
        }),
      ),
    onSuccess: async () => {
      setOpen(false)
      await queryClient.invalidateQueries({ queryKey: memberKeys.list(workspaceId) })
    },
  })
  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (next) mutation.reset()
        setOpen(next)
      }}
    >
      <AlertDialogTrigger
        render={
          <Button variant="ghost" size="sm" aria-label={t('members.removeLabel', { name: member.display_name })}>
            {t('members.remove')}
          </Button>
        }
      />
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('members.removeTitle', { name: member.display_name })}</AlertDialogTitle>
          <AlertDialogDescription>{t('members.removeText')}</AlertDialogDescription>
        </AlertDialogHeader>
        <FormError error={mutation.isError ? errorText(mutation.error) : null} />
        <AlertDialogFooter>
          <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction variant="destructive" disabled={mutation.isPending} onClick={() => mutation.mutate()}>
            {t('members.remove')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
