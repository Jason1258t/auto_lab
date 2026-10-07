// The works of a workspace. Members see all; visitors of a public
// workspace see only accepted ones (the backend filters).
import { useTranslation } from 'react-i18next'

import { useWorks, WorkList } from '@/entities/work'
import type { Workspace } from '@/entities/workspace'
import { errorText } from '@/shared/api'
import { Card, CardContent, CardHeader, CardTitle, FormError } from '@/shared/ui'

export function WorkspaceWorks({ workspace }: { workspace: Workspace }) {
  const { t } = useTranslation()
  const works = useWorks(workspace.id)
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('work.title')}</CardTitle>
      </CardHeader>
      <CardContent>
        {works.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
        {works.isError && <FormError error={errorText(works.error)} />}
        {works.data && <WorkList works={works.data} />}
      </CardContent>
    </Card>
  )
}
