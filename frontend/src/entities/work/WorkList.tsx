import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { formatDateTime } from '@/shared/lib/format'

import type { WorkListItem } from './model'

export function WorkList({ works }: { works: WorkListItem[] }) {
  const { t } = useTranslation()
  if (!works.length) return <p className="text-muted-foreground">{t('work.empty')}</p>
  return (
    <ul className="divide-y divide-border">
      {works.map((work) => (
        <li key={work.task_id} className="grid gap-1 py-3">
          <Link to={`/works/${work.task_id}`} className="font-medium hover:underline">
            {work.title}
          </Link>
          {work.summary && <p className="line-clamp-2 text-sm text-muted-foreground">{work.summary}</p>}
          <span className="text-xs text-muted-foreground">{formatDateTime(work.updated_at)}</span>
        </li>
      ))}
    </ul>
  )
}
