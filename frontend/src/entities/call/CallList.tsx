import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { formatDuration } from '@/shared/lib/format'
import { Badge } from '@/shared/ui'

import { CallLogError, CallLogView } from './CallLogView'
import { useCallLog, type LlmCall } from './model'

const FINISHED: LlmCall['status'][] = ['done', 'failed', 'cancelled']

function seconds(call: LlmCall): number | null {
  if (!call.started_at || !call.finished_at) return null
  return Math.max(0, Math.round((Date.parse(call.finished_at) - Date.parse(call.started_at)) / 100) / 10)
}

function CallRow({ call }: { call: LlmCall }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const finished = FINISHED.includes(call.status)
  const log = useCallLog(call.id, open, finished)
  const took = seconds(call)
  const facts = [
    call.attempt > 1 && t('calls.attempt', { n: call.attempt }),
    call.input_tokens !== null && t('calls.tokens', { input: call.input_tokens, output: call.output_tokens ?? 0 }),
    took !== null && formatDuration(took),
    call.finish_reason === 'length' && t('calls.cutOff'),
    call.valid_json === false && t('calls.invalidJson'),
  ].filter(Boolean)
  return (
    <li className="grid gap-2 rounded-md border border-border p-2">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex flex-wrap items-center gap-2 text-left text-sm"
      >
        {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
        <span className="font-medium">{t('calls.call', { id: call.id })}</span>
        <Badge variant={call.status === 'failed' ? 'destructive' : 'outline'}>{t(`calls.status.${call.status}`)}</Badge>
        <span className="text-muted-foreground">{facts.join(' · ')}</span>
      </button>
      {call.error && <p className="text-sm text-destructive">{call.error}</p>}
      {open && (
        <>
          {log.isPending && <p className="text-sm text-muted-foreground">{t('common.loading')}</p>}
          {log.isError && <CallLogError error={log.error} />}
          {log.data && <CallLogView log={log.data} />}
        </>
      )}
    </li>
  )
}

/** The calls of one step. Click a call to see its prompt and answer. */
export function CallList({ calls }: { calls: LlmCall[] }) {
  if (!calls.length) return null
  return (
    <ul className="mt-2 grid gap-2">
      {calls.map((call) => (
        <CallRow key={call.id} call={call} />
      ))}
    </ul>
  )
}
