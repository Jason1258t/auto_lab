import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { api, call, type components } from '@/shared/api'

export type Workspace = components['schemas']['WorkspaceOut']
export type WorkspaceScope = 'mine' | 'public' | 'free'

// All keys start with 'workspaces', so one invalidate refreshes lists and pages.
export const workspaceKeys = {
  all: ['workspaces'] as const,
  list: (scope: WorkspaceScope) => ['workspaces', 'list', scope] as const,
  detail: (id: number) => ['workspaces', 'detail', id] as const,
}

export function useWorkspaces(scope: WorkspaceScope) {
  return useQuery({
    queryKey: workspaceKeys.list(scope),
    queryFn: () => call(api.GET('/api/v1/workspaces', { params: { query: { scope } } })),
  })
}

export function useWorkspace(id: number) {
  return useQuery({
    queryKey: workspaceKeys.detail(id),
    queryFn: () =>
      call(api.GET('/api/v1/workspaces/{workspace_id}', { params: { path: { workspace_id: id } } })),
  })
}

/** What the current user may do with the workspace itself. The backend
 *  checks the same rules (services/permissions.py); this only hides
 *  buttons that would fail. */
export function workspaceRights(w: Workspace) {
  const archived = w.archived_at !== null
  const isPublic = w.visibility === 'public'
  return {
    edit: w.is_owner && !archived,
    archive: w.is_owner && !archived,
    unarchive: w.is_owner && archived,
    makePublic: w.is_owner && !archived && !isPublic,
    take: isPublic && archived && w.owner_id === null,
    leave: !w.is_owner && w.my_roles.length > 0,
    delete: w.is_owner,
  }
}

/** Short facts: public or private, archived, owner. */
export function useWorkspaceFacts(workspace: Workspace): string {
  const { t } = useTranslation()
  return [
    t(workspace.visibility === 'public' ? 'workspaces.public' : 'workspaces.private'),
    workspace.archived_at && t('workspaces.archived'),
    workspace.is_owner && t('workspaces.owner'),
    workspace.owner_id === null && workspace.archived_at && t('workspaces.free'),
  ]
    .filter(Boolean)
    .join(' · ')
}
