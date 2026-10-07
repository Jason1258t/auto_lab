import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { api, call, type components } from '@/shared/api'

export type Workspace = components['schemas']['WorkspaceOut']
export type WorkspaceScope = 'mine' | 'public' | 'free'
/** Roles given on top of the base `member` role. */
export type ExtraRole = 'editor' | 'reviewer'
export const EXTRA_ROLES: ExtraRole[] = ['editor', 'reviewer']

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
  const isMember = w.my_roles.includes('member')
  const isEditor = w.my_roles.includes('editor')
  return {
    edit: w.is_owner && !archived,
    archive: w.is_owner && !archived,
    unarchive: w.is_owner && archived,
    makePublic: w.is_owner && !archived && !isPublic,
    take: isPublic && archived && w.owner_id === null,
    leave: !w.is_owner && isMember,
    delete: w.is_owner,
    /** Members, tasks, files (admins too, see `Me.is_admin`). */
    seeInside: w.is_owner || isMember,
    addMembers: w.is_owner && !archived,
    removeMembers: w.is_owner && !archived,
    editTasks: (w.is_owner || isEditor) && !archived,
    editFiles: (w.is_owner || isEditor) && !archived,
    /** The activity log (admins too). */
    readActivity: w.is_owner || isEditor,
    /** Owner: editor and reviewer; editor: reviewer only. */
    manageRole: (role: ExtraRole) =>
      !archived && (w.is_owner || (role === 'reviewer' && isEditor)),
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
