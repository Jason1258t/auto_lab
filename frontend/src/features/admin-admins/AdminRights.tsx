// Give or take admin rights by user id (an admin cannot remove their own).
// There is no user search yet, so the admin types the user id.
import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { api, call, errorText } from '@/shared/api'
import { Alert, AlertDescription, Button, FormError, Input, Label } from '@/shared/ui'

export function AdminRights() {
  const { t } = useTranslation()
  const [userId, setUserId] = useState('')
  const [done, setDone] = useState<string | null>(null)
  const mutation = useMutation({
    mutationFn: async (grant: boolean) => {
      const options = { params: { path: { user_id: Number(userId) } } }
      if (grant) await call(api.POST('/api/v1/admin/admins/{user_id}', options))
      else await call(api.DELETE('/api/v1/admin/admins/{user_id}', options))
      return grant
    },
    onMutate: () => setDone(null),
    onSuccess: (grant) => setDone(t(grant ? 'admin.granted' : 'admin.revoked', { id: userId })),
  })
  const submit = (grant: boolean) => (event: FormEvent) => {
    event.preventDefault()
    mutation.mutate(grant)
  }
  return (
    <form onSubmit={submit(true)} className="grid max-w-md gap-3">
      <div className="grid gap-2">
        <Label htmlFor="admin-user-id">{t('admin.userId')}</Label>
        <Input id="admin-user-id" type="number" min={1} value={userId} onChange={(e) => setUserId(e.target.value)} required />
      </div>
      <FormError error={mutation.isError ? errorText(mutation.error) : null} />
      {done && (
        <Alert>
          <AlertDescription>{done}</AlertDescription>
        </Alert>
      )}
      <div className="flex gap-2">
        <Button type="submit" disabled={mutation.isPending || !userId}>
          {t('admin.grant')}
        </Button>
        <Button type="button" variant="destructive" disabled={mutation.isPending || !userId} onClick={submit(false)}>
          {t('admin.revoke')}
        </Button>
      </div>
    </form>
  )
}
