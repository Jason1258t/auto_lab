import { useQuery } from '@tanstack/react-query'

import { api, call, type components } from '@/shared/api'

export type WorkspaceFile = components['schemas']['FileOut']

export const fileKeys = {
  list: (workspaceId: number) => ['workspaces', 'files', workspaceId] as const,
}

export function useFiles(workspaceId: number) {
  return useQuery({
    queryKey: fileKeys.list(workspaceId),
    queryFn: () =>
      call(
        api.GET('/api/v1/workspaces/{workspace_id}/files', {
          params: { path: { workspace_id: workspaceId } },
        }),
      ),
  })
}
