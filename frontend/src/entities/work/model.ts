import { useQuery } from '@tanstack/react-query'

import { api, ApiError, call, type components } from '@/shared/api'

export type Work = components['schemas']['WorkOut']
export type WorkListItem = components['schemas']['WorkListItem']
export type Source = components['schemas']['SourceOut']

export const workKeys = {
  one: (taskId: number) => ['tasks', taskId, 'work'] as const,
  list: (workspaceId: number) => ['workspaces', 'works', workspaceId] as const,
}

/** The work of a task, or null while there is none yet (404). */
export function useWork(taskId: number, enabled = true) {
  return useQuery({
    queryKey: workKeys.one(taskId),
    queryFn: async () => {
      try {
        return await call(api.GET('/api/v1/tasks/{task_id}/work', { params: { path: { task_id: taskId } } }))
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null
        throw error
      }
    },
    enabled,
  })
}

export function useWorks(workspaceId: number) {
  return useQuery({
    queryKey: workKeys.list(workspaceId),
    queryFn: () =>
      call(
        api.GET('/api/v1/workspaces/{workspace_id}/works', {
          params: { path: { workspace_id: workspaceId } },
        }),
      ),
  })
}

/** How many sentences the write step marked "no source". */
export function unsourcedCount(text: string): number {
  return text.split('⚠ no source').length - 1
}
