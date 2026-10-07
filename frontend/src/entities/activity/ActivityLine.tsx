import { useTranslation } from 'react-i18next'

import { formatDateTime } from '@/shared/lib/format'

import type { ActivityEvent } from './model'

/** "Ann added bob · 7 Oct 2026, 13:40". Unknown actions fall back to
 *  the action name, so a new backend action does not break the page. */
export function ActivityLine({ event }: { event: ActivityEvent }) {
  const { t } = useTranslation()
  const role = typeof event.details?.role === 'string' ? t(`roles.${event.details.role}`) : ''
  // A member who left by themselves is also `member_removed`.
  const action = event.action === 'member_removed' && event.details?.left ? 'member_left' : event.action
  const text = t(`activity.${action}`, {
    defaultValue: event.action,
    actor: event.actor_name ?? t('activity.someone'),
    target: event.target_label ?? '',
    role,
  })
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-2 py-2">
      <span>{text}</span>
      <time dateTime={event.occurred_at} className="text-xs text-muted-foreground">
        {formatDateTime(event.occurred_at)}
      </time>
    </div>
  )
}
