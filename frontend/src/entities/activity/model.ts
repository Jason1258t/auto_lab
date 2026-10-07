import { useQuery } from '@tanstack/react-query'

import { api, call, type components } from '@/shared/api'

export type ActivityEvent = components['schemas']['ActivityEventOut']

export const activityKeys = {
  list: (workspaceId: number) => ['workspaces', 'activity', workspaceId] as const,
}

export function useActivity(workspaceId: number) {
  return useQuery({
    queryKey: activityKeys.list(workspaceId),
    queryFn: () =>
      call(
        api.GET('/api/v1/workspaces/{workspace_id}/activity', {
          params: { path: { workspace_id: workspaceId }, query: { limit: 100 } },
        }),
      ),
  })
}
