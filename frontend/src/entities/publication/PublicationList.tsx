import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { formatDateTime } from '@/shared/lib/format'

import type { Publication } from './model'

export function PublicationList({ publications }: { publications: Publication[] }) {
  const { t } = useTranslation()
  if (!publications.length) return <p className="text-muted-foreground">{t('feed.empty')}</p>
  return (
    <ul className="divide-y divide-border">
      {publications.map((p) => (
        <li key={p.id} className="grid gap-1 py-4">
          <Link to={`/publications/${p.id}`} className="font-heading text-xl font-semibold hover:underline">
            {p.title}
          </Link>
          {p.description && <p className="text-muted-foreground">{p.description}</p>}
          <span className="text-sm text-muted-foreground">
            <Link to={`/publishers/${p.publisher.id}`} className="hover:text-foreground hover:underline">
              {p.publisher.name}
            </Link>{' '}
            · {formatDateTime(p.published_at)}
          </span>
        </li>
      ))}
    </ul>
  )
}
