// The public feed: published works, newest first. Open to everyone.
import { useTranslation } from 'react-i18next'

import { PublicationList, usePublications } from '@/entities/publication'
import { errorText } from '@/shared/api'
import { FormError } from '@/shared/ui'

export function FeedPage() {
  const { t } = useTranslation()
  const feed = usePublications()
  return (
    <section className="grid gap-6">
      <header className="grid gap-1">
        <h1 className="font-heading text-3xl font-semibold">{t('feed.title')}</h1>
        <p className="text-muted-foreground">{t('feed.text')}</p>
      </header>
      {feed.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
      {feed.isError && <FormError error={errorText(feed.error)} />}
      {feed.data && <PublicationList publications={feed.data} />}
    </section>
  )
}
