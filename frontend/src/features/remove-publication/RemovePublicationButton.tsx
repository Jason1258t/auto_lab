// Admins remove a publication from the feed (moderation). The work itself
// stays in its workspace.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'

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

export function RemovePublicationButton({ id, title }: { id: number; title: string }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const mutation = useMutation({
    mutationFn: () => call(api.DELETE('/api/v1/admin/publications/{publication_id}', { params: { path: { publication_id: id } } })),
    onSuccess: async () => {
      setOpen(false)
      queryClient.removeQueries({ queryKey: ['publications', id] })
      await queryClient.invalidateQueries({ queryKey: ['publications'] })
      void navigate('/feed')
    },
  })
  return (
    <AlertDialog open={open} onOpenChange={(next) => { if (next) mutation.reset(); setOpen(next) }}>
      <AlertDialogTrigger render={<Button variant="destructive">{t('admin.removePublication')}</Button>} />
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('admin.removePublicationTitle', { title })}</AlertDialogTitle>
          <AlertDialogDescription>{t('admin.removePublicationText')}</AlertDialogDescription>
        </AlertDialogHeader>
        <FormError error={mutation.isError ? errorText(mutation.error) : null} />
        <AlertDialogFooter>
          <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction variant="destructive" disabled={mutation.isPending} onClick={() => mutation.mutate()}>
            {t('admin.removePublication')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
