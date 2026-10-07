// Upload one or more files to the workspace (owner and editors).
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useRef, type ChangeEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { fileKeys } from '@/entities/file'
import { api, call, errorText } from '@/shared/api'
import { Button, FormError } from '@/shared/ui'

async function upload(workspaceId: number, file: File) {
  const form = new FormData()
  form.append('file', file)
  return call(
    api.POST('/api/v1/workspaces/{workspace_id}/files', {
      params: { path: { workspace_id: workspaceId } },
      // The generated type says `string`; the real body is multipart.
      body: {} as never,
      bodySerializer: () => form,
    }),
  )
}

export function UploadFileButton({ workspaceId }: { workspaceId: number }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const mutation = useMutation({
    // One by one: a failed file stops the rest and names itself.
    mutationFn: async (files: File[]) => {
      for (const file of files) {
        try {
          await upload(workspaceId, file)
        } catch (error) {
          throw new Error(t('files.uploadFailed', { name: file.name, reason: errorText(error) }))
        }
      }
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: fileKeys.list(workspaceId) }),
  })
  const onChange = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? [])
    event.target.value = '' // the same file can be chosen again
    if (files.length) mutation.mutate(files)
  }
  return (
    <div className="grid gap-2">
      <input ref={input} type="file" multiple hidden onChange={onChange} data-testid="file-input" />
      <div>
        <Button onClick={() => input.current?.click()} disabled={mutation.isPending}>
          {mutation.isPending ? t('files.uploading') : t('files.upload')}
        </Button>
      </div>
      <FormError error={mutation.isError ? mutation.error.message : null} />
    </div>
  )
}
