// One publication: the published text with its sources and quotes.
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'

import { usePublication } from '@/entities/publication'
import { useSession } from '@/entities/session'
import { WorkView } from '@/entities/work'
import { RemovePublicationButton } from '@/features/remove-publication'
import { ApiError, errorText } from '@/shared/api'
import { formatDateTime } from '@/shared/lib/format'
import { FormError } from '@/shared/ui'

export function PublicationPage() {
  const { t } = useTranslation()
  const id = Number(useParams().publicationId)
  const publication = usePublication(id)
  const p = publication.data
  const { me } = useSession()
  return (
    <section className="grid gap-6">
      <Link to="/feed" className="text-sm text-muted-foreground hover:text-foreground">
        ← {t('nav.feed')}
      </Link>
      {publication.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
      {publication.isError &&
        (publication.error instanceof ApiError && publication.error.status === 404 ? (
          <p className="text-muted-foreground">{t('feed.notFound')}</p>
        ) : (
          <FormError error={errorText(publication.error)} />
        ))}
      {p && (
        <>
          <header className="grid gap-1">
            <h1 className="font-heading text-3xl font-semibold">{p.title}</h1>
            {p.description && <p className="text-muted-foreground">{p.description}</p>}
            <p className="text-sm text-muted-foreground">
              <Link to={`/publishers/${p.publisher.id}`} className="hover:text-foreground hover:underline">
                {p.publisher.name}
              </Link>{' '}
              · {formatDateTime(p.published_at)}
            </p>
            {me?.is_admin && (
              <div>
                <RemovePublicationButton id={p.id} title={p.title} />
              </div>
            )}
          </header>
          <WorkView work={p} forReview={false} />
        </>
      )}
    </section>
  )
}
