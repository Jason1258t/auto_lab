// Data only admins can read: all models (also unavailable ones), model
// providers, and the global activity log.
import { useQuery } from '@tanstack/react-query'

import { api, call, type components } from '@/shared/api'

export type AdminModel = components['schemas']['ModelOut']
export type Provider = components['schemas']['ProviderOut']
export type AdminPipeline = components['schemas']['AdminPipelineOut']

export const adminKeys = {
  models: ['admin', 'models'] as const,
  providers: ['admin', 'providers'] as const,
  activity: ['admin', 'activity'] as const,
  pipelines: ['admin', 'pipelines'] as const,
  pipelineFile: (versionId: number) => ['admin', 'pipeline-file', versionId] as const,
}

export function useAdminModels() {
  return useQuery({ queryKey: adminKeys.models, queryFn: () => call(api.GET('/api/v1/admin/models')) })
}

export function useProviders() {
  return useQuery({ queryKey: adminKeys.providers, queryFn: () => call(api.GET('/api/v1/admin/model-providers')) })
}

export function useGlobalActivity() {
  return useQuery({
    queryKey: adminKeys.activity,
    queryFn: () => call(api.GET('/api/v1/admin/activity', { params: { query: { limit: 100 } } })),
  })
}

export function useAdminPipelines() {
  return useQuery({ queryKey: adminKeys.pipelines, queryFn: () => call(api.GET('/api/v1/admin/pipelines')) })
}

/** The YAML text of one version; loaded only when someone opens it. */
export function usePipelineFile(versionId: number, enabled: boolean) {
  return useQuery({
    queryKey: adminKeys.pipelineFile(versionId),
    queryFn: () =>
      call(
        api.GET('/api/v1/admin/pipeline-versions/{version_id}/file', {
          params: { path: { version_id: versionId } },
          parseAs: 'text',
        }),
      ) as Promise<string>,
    enabled,
    staleTime: Infinity, // a version file never changes
  })
}
