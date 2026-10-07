import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

export function NotFoundPage() {
  const { t } = useTranslation()
  return (
    <section className="grid gap-4 p-8">
      <h1 className="font-heading text-3xl font-semibold">{t('notFound.title')}</h1>
      <Link to="/" className="text-primary underline-offset-4 hover:underline">
        {t('notFound.back')}
      </Link>
    </section>
  )
}
