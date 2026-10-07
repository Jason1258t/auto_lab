// Download a workspace file, or remove it (asks first).
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { fileKeys, type WorkspaceFile } from '@/entities/file'
import { api, call, errorText } from '@/shared/api'
import { saveBlob } from '@/shared/lib/download'
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

type Props = { workspaceId: number; file: WorkspaceFile }

export function DownloadFileButton({ workspaceId, file }: Props) {
  const { t } = useTranslation()
  const mutation = useMutation({
    mutationFn: async () => {
      const blob = await call(
        api.GET('/api/v1/workspaces/{workspace_id}/files/{file_id}/download', {
          params: { path: { workspace_id: workspaceId, file_id: file.id } },
          parseAs: 'blob',
        }),
      )
      saveBlob(blob as Blob, file.original_name)
    },
  })
  return (
    <span className="flex items-center gap-2">
      <Button
        variant="outline"
        size="sm"
        disabled={mutation.isPending}
        onClick={() => mutation.mutate()}
        aria-label={t('files.downloadLabel', { name: file.original_name })}
      >
        {t('files.download')}
      </Button>
      {mutation.isError && (
        <span role="alert" className="text-xs text-destructive">
          {errorText(mutation.error)}
        </span>
      )}
    </span>
  )
}

export function RemoveFileButton({ workspaceId, file }: Props) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const mutation = useMutation({
    mutationFn: () =>
      call(
        api.DELETE('/api/v1/workspaces/{workspace_id}/files/{file_id}', {
          params: { path: { workspace_id: workspaceId, file_id: file.id } },
        }),
      ),
    onSuccess: async () => {
      setOpen(false)
      await queryClient.invalidateQueries({ queryKey: fileKeys.list(workspaceId) })
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
          <Button variant="ghost" size="sm" aria-label={t('files.removeLabel', { name: file.original_name })}>
            {t('files.remove')}
          </Button>
        }
      />
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('files.removeTitle', { name: file.original_name })}</AlertDialogTitle>
          <AlertDialogDescription>{t('files.removeText')}</AlertDialogDescription>
        </AlertDialogHeader>
        <FormError error={mutation.isError ? errorText(mutation.error) : null} />
        <AlertDialogFooter>
          <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction variant="destructive" disabled={mutation.isPending} onClick={() => mutation.mutate()}>
            {t('files.remove')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
