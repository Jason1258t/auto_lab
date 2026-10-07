// The workspace activity log: the last 100 events (owner, editors, admins).
import { useTranslation } from 'react-i18next'

import { ActivityLine, useActivity } from '@/entities/activity'
import type { Workspace } from '@/entities/workspace'
import { errorText } from '@/shared/api'
import { Card, CardContent, CardHeader, CardTitle, FormError } from '@/shared/ui'

export function WorkspaceActivity({ workspace }: { workspace: Workspace }) {
  const { t } = useTranslation()
  const events = useActivity(workspace.id)
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('activity.title')}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        {events.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
        {events.isError && <FormError error={errorText(events.error)} />}
        {events.data?.length === 0 && <p className="text-muted-foreground">{t('activity.empty')}</p>}
        <ul className="divide-y divide-border text-sm">
          {events.data?.map((event) => (
            <li key={event.id}>
              <ActivityLine event={event} />
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}
