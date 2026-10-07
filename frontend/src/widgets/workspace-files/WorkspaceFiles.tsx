// Workspace files: everyone inside can list and download; owner and
// editors can upload and remove.
import { useTranslation } from 'react-i18next'

import { useFiles } from '@/entities/file'
import { workspaceRights, type Workspace } from '@/entities/workspace'
import { DownloadFileButton, RemoveFileButton } from '@/features/file-actions'
import { UploadFileButton } from '@/features/file-upload'
import { errorText } from '@/shared/api'
import { formatBytes, formatDateTime } from '@/shared/lib/format'
import { Card, CardContent, CardHeader, CardTitle, FormError } from '@/shared/ui'

export function WorkspaceFiles({ workspace }: { workspace: Workspace }) {
  const { t } = useTranslation()
  const files = useFiles(workspace.id)
  const canEdit = workspaceRights(workspace).editFiles
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('files.title')}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        {canEdit && <UploadFileButton workspaceId={workspace.id} />}
        {files.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
        {files.isError && <FormError error={errorText(files.error)} />}
        {files.data?.length === 0 && <p className="text-muted-foreground">{t('files.empty')}</p>}
        <ul className="divide-y divide-border">
          {files.data?.map((file) => (
            <li key={file.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
              <div className="grid min-w-0">
                <span className="truncate font-medium">{file.original_name}</span>
                <span className="text-sm text-muted-foreground">
                  {formatBytes(file.size_bytes)} · {formatDateTime(file.created_at)}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <DownloadFileButton workspaceId={workspace.id} file={file} />
                {canEdit && <RemoveFileButton workspaceId={workspace.id} file={file} />}
              </div>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}
