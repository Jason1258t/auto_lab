import { useQuery } from '@tanstack/react-query'

import { api, call, type components } from '@/shared/api'

export type Task = components['schemas']['TaskOut']
export type TaskDetail = components['schemas']['TaskDetailOut']
export type TaskStatus = components['schemas']['TaskStatus']
export type TaskStep = components['schemas']['TaskStepOut']
export type PlanStep = components['schemas']['PlanStepOut']

export const taskKeys = {
  list: (workspaceId: number) => ['workspaces', 'tasks', workspaceId] as const,
  detail: (id: number) => ['tasks', id] as const,
}

/** While the worker is busy, the page asks again every few seconds
 *  (backend_spec.md §7: polling now, SSE later). */
export const POLL_MS = 3000
export const ACTIVE: TaskStatus[] = ['queued', 'running']
export const CANCELLABLE: TaskStatus[] = ['queued', 'running', 'in_review']

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

export function useTask(id: number) {
  return useQuery({
    queryKey: taskKeys.detail(id),
    queryFn: () => call(api.GET('/api/v1/tasks/{task_id}', { params: { path: { task_id: id } } })),
    refetchInterval: (query) =>
      query.state.data && ACTIVE.includes(query.state.data.status) ? POLL_MS : false,
  })
}

/** One line per step. Before the worker starts, only the plan exists:
 *  all steps are shown as pending. */
export function stepRows(task: TaskDetail): TaskStep[] {
  if (task.steps.length) return task.steps
  return task.plan.map((plan, index) => ({
    step_index: index,
    step_id: plan.step_id,
    kind: plan.kind,
    status: 'pending',
    summary: null,
    review_id: null,
    started_at: null,
    finished_at: null,
  }))
}
