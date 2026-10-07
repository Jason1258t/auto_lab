// The full prompt and answer of one model call. Texts can contain web
// pages (untrusted), so they are shown only as plain text, never as HTML.
import { useTranslation } from 'react-i18next'

import { errorText } from '@/shared/api'
import { FormError } from '@/shared/ui'

import type { CallLog } from './model'

/** Pretty JSON if the text is JSON, else the text as it is. */
function pretty(text: string): string {
  try {
    return JSON.stringify(JSON.parse(text), null, 2)
  } catch {
    return text
  }
}

function Block({ label, text }: { label: string; text: string }) {
  return (
    <div className="grid gap-1">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <pre className="max-h-80 overflow-auto rounded-md bg-muted p-2 text-xs whitespace-pre-wrap break-words">
        {text}
      </pre>
    </div>
  )
}

export function CallLogView({ log }: { log: CallLog }) {
  const { t } = useTranslation()
  return (
    <div className="grid gap-3">
      {log.request.messages.map((message, i) => (
        <Block key={i} label={t(`calls.role.${message.role}`, { defaultValue: message.role })} text={message.content} />
      ))}
      {log.request.schema && <Block label={t('calls.schema')} text={JSON.stringify(log.request.schema, null, 2)} />}
      {log.response ? (
        <Block label={t('calls.answer')} text={pretty(log.response.text)} />
      ) : (
        <p className="text-sm text-muted-foreground">{t('calls.noAnswer')}</p>
      )}
    </div>
  )
}

export function CallLogError({ error }: { error: unknown }) {
  return <FormError error={errorText(error)} />
}
