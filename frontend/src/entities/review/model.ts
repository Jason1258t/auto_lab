import { useQuery } from '@tanstack/react-query'

import { api, call, type components } from '@/shared/api'

export type Review = components['schemas']['ReviewOut']

export const reviewKeys = {
  list: (taskId: number) => ['tasks', taskId, 'reviews'] as const,
}

export function useReviews(taskId: number) {
  return useQuery({
    queryKey: reviewKeys.list(taskId),
    queryFn: () => call(api.GET('/api/v1/tasks/{task_id}/reviews', { params: { path: { task_id: taskId } } })),
  })
}
