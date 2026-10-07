import { useQuery } from '@tanstack/react-query'

import { api, call, type components } from '@/shared/api'

export type LlmCall = components['schemas']['CallOut']
export type CallLog = components['schemas']['CallLogOut']

export const callKeys = {
  list: (taskId: number) => ['tasks', taskId, 'calls'] as const,
  log: (callId: number) => ['calls', callId, 'log'] as const,
}

/** All model calls of a task. `pollMs` while the task runs. */
export function useCalls(taskId: number, pollMs: number | false) {
  return useQuery({
    queryKey: callKeys.list(taskId),
    queryFn: () => call(api.GET('/api/v1/tasks/{task_id}/calls', { params: { path: { task_id: taskId } } })),
    refetchInterval: pollMs,
  })
}

/** The full prompt and answer, loaded only when someone opens it. A
 *  finished call's log does not change, so it is never refetched. */
export function useCallLog(callId: number, enabled: boolean, finished: boolean) {
  return useQuery({
    queryKey: callKeys.log(callId),
    queryFn: () => call(api.GET('/api/v1/calls/{call_id}/log', { params: { path: { call_id: callId } } })),
    enabled,
    staleTime: finished ? Infinity : 0,
  })
}
