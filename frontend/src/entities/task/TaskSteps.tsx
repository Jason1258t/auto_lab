import { CircleCheck, CircleDashed, LoaderCircle } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import type { TaskStep } from './model'

function seconds(step: TaskStep): number | null {
  if (!step.started_at || !step.finished_at) return null
  return Math.max(0, Math.round((Date.parse(step.finished_at) - Date.parse(step.started_at)) / 1000))
}

function StatusIcon({ status }: { status: TaskStep['status'] }) {
  const { t } = useTranslation()
  const label = t(`stepStatus.${status}`)
  if (status === 'done') return <CircleCheck className="size-5 text-primary" aria-label={label} />
  if (status === 'running') return <LoaderCircle className="size-5 animate-spin text-primary" aria-label={label} />
  return <CircleDashed className="size-5 text-muted-foreground" aria-label={label} />
}

/** The steps in order. Rows of a revision (after a rejected review)
 *  start with a small heading. `extra` renders more under a step (calls). */
export function TaskSteps({ steps, extra }: { steps: TaskStep[]; extra?: (step: TaskStep) => ReactNode }) {
  const { t } = useTranslation()
  return (
    <ol className="grid">
      {steps.map((step, i) => {
        const revision = step.review_id !== null && step.review_id !== steps[i - 1]?.review_id
        const took = seconds(step)
        return (
          <li key={step.step_index} className="grid gap-1">
            {revision && (
              <p className="mt-3 border-t border-border pt-3 text-xs font-medium tracking-wide text-muted-foreground uppercase">
                {t('task.revision')}
              </p>
            )}
            <div className="flex items-start gap-3 py-2">
              <StatusIcon status={step.status} />
              <div className="grid min-w-0 flex-1 gap-0.5">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="font-medium">
                    {step.step_id ?? t('task.stepNumber', { n: step.step_index + 1 })}
                    {step.kind && step.kind !== step.step_id && (
                      <span className="ml-2 text-sm font-normal text-muted-foreground">{step.kind}</span>
                    )}
                  </span>
                  {took !== null && (
                    <span className="text-xs text-muted-foreground">{t('task.seconds', { count: took })}</span>
                  )}
                </div>
                {step.summary && <p className="text-sm text-muted-foreground">{step.summary}</p>}
                {extra?.(step)}
              </div>
            </div>
          </li>
        )
      })}
    </ol>
  )
}
