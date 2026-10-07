import { Card, CardDescription, CardHeader, CardTitle } from '@/shared/ui'

import { useWorkspaceFacts, type Workspace } from './model'

export function WorkspaceCard({ workspace }: { workspace: Workspace }) {
  const facts = useWorkspaceFacts(workspace)
  return (
    <Card className="h-full transition-colors hover:bg-muted">
      <CardHeader>
        <CardTitle>{workspace.name}</CardTitle>
        <CardDescription>{facts}</CardDescription>
        {workspace.description && (
          <p className="line-clamp-2 text-sm text-muted-foreground">{workspace.description}</p>
        )}
      </CardHeader>
    </Card>
  )
}
