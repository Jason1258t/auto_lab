import { useTranslation } from 'react-i18next'

import { Card, CardDescription, CardHeader, CardTitle } from '@/shared/ui'

import type { Workspace } from './model'

export function WorkspaceCard({ workspace }: { workspace: Workspace }) {
  const { t } = useTranslation()
  const facts = [
    t(workspace.visibility === 'public' ? 'workspaces.public' : 'workspaces.private'),
    workspace.archived_at && t('workspaces.archived'),
    workspace.is_owner && t('workspaces.owner'),
  ].filter(Boolean)
  return (
    <Card>
      <CardHeader>
        <CardTitle>{workspace.name}</CardTitle>
        <CardDescription>{facts.join(' · ')}</CardDescription>
      </CardHeader>
    </Card>
  )
}
