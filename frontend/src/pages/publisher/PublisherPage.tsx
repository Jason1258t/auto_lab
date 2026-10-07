// A publisher and everything it has published.
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router'

import { PublicationList, usePublications, usePublisher } from '@/entities/publication'
import { ApiError, errorText } from '@/shared/api'
import { FormError } from '@/shared/ui'

export function PublisherPage() {
  const { t } = useTranslation()
  const id = Number(useParams().publisherId)
  const publisher = usePublisher(id)
  const publications = usePublications(id)
  return (
    <section className="grid gap-6">
      {publisher.isError &&
        (publisher.error instanceof ApiError && publisher.error.status === 404 ? (
          <p className="text-muted-foreground">{t('feed.publisherNotFound')}</p>
        ) : (
          <FormError error={errorText(publisher.error)} />
        ))}
      {publisher.data && (
        <header className="grid gap-1">
          <h1 className="font-heading text-3xl font-semibold">{publisher.data.name}</h1>
          {publisher.data.description && <p className="text-muted-foreground">{publisher.data.description}</p>}
        </header>
      )}
      {publications.data && <PublicationList publications={publications.data} />}
    </section>
  )
}
