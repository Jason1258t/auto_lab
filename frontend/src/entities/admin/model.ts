// Data only admins can read: all models (also unavailable ones), model
// providers, and the global activity log.
import { useQuery } from '@tanstack/react-query'

import { api, call, type components } from '@/shared/api'

export type AdminModel = components['schemas']['ModelOut']
export type Provider = components['schemas']['ProviderOut']

export const adminKeys = {
  models: ['admin', 'models'] as const,
  providers: ['admin', 'providers'] as const,
  activity: ['admin', 'activity'] as const,
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
