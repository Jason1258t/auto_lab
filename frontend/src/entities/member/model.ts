import { useQuery } from '@tanstack/react-query'

import { api, call, type components } from '@/shared/api'

export type Member = components['schemas']['MemberOut']

export const memberKeys = {
  list: (workspaceId: number) => ['workspaces', 'members', workspaceId] as const,
}

export function useMembers(workspaceId: number) {
  return useQuery({
    queryKey: memberKeys.list(workspaceId),
    queryFn: () =>
      call(
        api.GET('/api/v1/workspaces/{workspace_id}/members', {
          params: { path: { workspace_id: workspaceId } },
        }),
      ),
  })
}
