import { useQuery } from '@tanstack/react-query'

import { api, call, type components } from '@/shared/api'

export type Publication = components['schemas']['PublicationOut']
export type PublicationDetail = components['schemas']['PublicationDetail']
export type Publisher = components['schemas']['PublisherOut']

export const publicationKeys = {
  feed: (publisherId: number | null) => ['publications', 'feed', publisherId] as const,
  one: (id: number) => ['publications', id] as const,
  publisher: (id: number) => ['publishers', id] as const,
  myPublishers: ['publishers', 'mine'] as const,
}

/** The public feed, newest first; one publisher's only if given. */
export function usePublications(publisherId: number | null = null) {
  return useQuery({
    queryKey: publicationKeys.feed(publisherId),
    queryFn: () =>
      call(
        api.GET('/api/v1/publications', {
          params: { query: publisherId === null ? {} : { publisher_id: publisherId } },
        }),
      ),
  })
}

export function usePublication(id: number) {
  return useQuery({
    queryKey: publicationKeys.one(id),
    queryFn: () =>
      call(api.GET('/api/v1/publications/{publication_id}', { params: { path: { publication_id: id } } })),
  })
}

export function usePublisher(id: number) {
  return useQuery({
    queryKey: publicationKeys.publisher(id),
    queryFn: () => call(api.GET('/api/v1/publishers/{publisher_id}', { params: { path: { publisher_id: id } } })),
  })
}

export function useMyPublishers(enabled = true) {
  return useQuery({
    queryKey: publicationKeys.myPublishers,
    queryFn: () => call(api.GET('/api/v1/publishers/mine')),
    enabled,
  })
}
