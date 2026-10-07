import { useTranslation } from 'react-i18next'

import { Badge } from '@/shared/ui'

import type { TaskStatus } from './model'

const VARIANT: Record<TaskStatus, 'default' | 'secondary' | 'outline' | 'destructive'> = {
  draft: 'outline',
  queued: 'secondary',
  running: 'secondary',
  in_review: 'default',
  done: 'secondary',
  cancelled: 'outline',
  failed: 'destructive',
}

export function TaskStatusBadge({ status }: { status: TaskStatus }) {
  const { t } = useTranslation()
  return <Badge variant={VARIANT[status]}>{t(`taskStatus.${status}`)}</Badge>
}
