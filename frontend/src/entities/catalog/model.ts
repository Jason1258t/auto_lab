// Pipelines and models a task can use. They change rarely: cached longer.
import { useQuery } from '@tanstack/react-query'

import { api, call, type components } from '@/shared/api'

export type Pipeline = components['schemas']['PipelineOut']
export type Model = components['schemas']['ModelOut']

const FIVE_MINUTES = 5 * 60 * 1000

export function usePipelines() {
  return useQuery({
    queryKey: ['catalog', 'pipelines'],
    queryFn: () => call(api.GET('/api/v1/pipelines')),
    staleTime: FIVE_MINUTES,
  })
}

export function useModels() {
  return useQuery({
    queryKey: ['catalog', 'models'],
    queryFn: () => call(api.GET('/api/v1/models')),
    staleTime: FIVE_MINUTES,
  })
}
