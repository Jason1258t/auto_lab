// The owner adds a person by username or email. They get the base
// `member` role; extra roles are given in the list.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { memberKeys } from '@/entities/member'
import { api, call, errorText } from '@/shared/api'
import { Button, FormError, Input, Label } from '@/shared/ui'

export function AddMemberForm({ workspaceId }: { workspaceId: number }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [who, setWho] = useState('')
  const mutation = useMutation({
    mutationFn: (usernameOrEmail: string) =>
      call(
        api.POST('/api/v1/workspaces/{workspace_id}/members', {
          params: { path: { workspace_id: workspaceId } },
          body: { username_or_email: usernameOrEmail },
        }),
      ),
    onSuccess: async () => {
      setWho('')
      await queryClient.invalidateQueries({ queryKey: memberKeys.list(workspaceId) })
    },
  })
  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    mutation.mutate(who.trim())
  }
  return (
    <form onSubmit={onSubmit} className="grid gap-2">
      <Label htmlFor="member-add">{t('members.addLabel')}</Label>
      <div className="flex gap-2">
        <Input
          id="member-add"
          value={who}
          onChange={(e) => setWho(e.target.value)}
          placeholder={t('members.addPlaceholder')}
          maxLength={320}
          required
        />
        <Button type="submit" disabled={mutation.isPending}>
          {t('members.add')}
        </Button>
      </div>
      <FormError error={mutation.isError ? errorText(mutation.error) : null} />
    </form>
  )
}
