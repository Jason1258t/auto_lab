import { useTranslation } from 'react-i18next'

import { formatDateTime } from '@/shared/lib/format'
import { Badge } from '@/shared/ui'

import type { Review } from './model'

/** All reviews of a task, oldest first. `nameOf` turns a user id into a
 *  name (the page knows the people of the workspace). */
export function ReviewList({ reviews, nameOf }: { reviews: Review[]; nameOf: (id: number | null) => string }) {
  const { t } = useTranslation()
  if (!reviews.length) return null
  return (
    <ol className="grid gap-3">
      {reviews.map((review) => (
        <li key={review.id} className="grid gap-1">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Badge variant={review.result === 'accepted' ? 'default' : 'destructive'}>{t(`review.${review.result}`)}</Badge>
            <span className="text-muted-foreground">
              {nameOf(review.reviewer_id)} · {formatDateTime(review.created_at)}
            </span>
          </div>
          {review.comment && <p className="text-sm whitespace-pre-wrap">{review.comment}</p>}
        </li>
      ))}
    </ol>
  )
}
