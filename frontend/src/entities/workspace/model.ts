import { useQuery } from '@tanstack/react-query'

import { api, call, type components } from '@/shared/api'

export type Workspace = components['schemas']['WorkspaceOut']
export type WorkspaceScope = 'mine' | 'public' | 'free'

export const workspaceKeys = {
  list: (scope: WorkspaceScope) => ['workspaces', scope] as const,
}

export function useWorkspaces(scope: WorkspaceScope) {
  return useQuery({
    queryKey: workspaceKeys.list(scope),
    queryFn: () => call(api.GET('/api/v1/workspaces', { params: { query: { scope } } })),
  })
}
