import { useQuery } from '@tanstack/react-query'

import { api, call, type components } from '@/shared/api'

export type Task = components['schemas']['TaskOut']
export type TaskStatus = components['schemas']['TaskStatus']

export const taskKeys = {
  list: (workspaceId: number) => ['workspaces', 'tasks', workspaceId] as const,
}

export function useTasks(workspaceId: number) {
  return useQuery({
    queryKey: taskKeys.list(workspaceId),
    queryFn: () =>
      call(
        api.GET('/api/v1/workspaces/{workspace_id}/tasks', {
          params: { path: { workspace_id: workspaceId } },
        }),
      ),
  })
}
