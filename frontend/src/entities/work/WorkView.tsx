import { useTranslation } from 'react-i18next'

import { formatDateTime } from '@/shared/lib/format'
import { Alert, AlertDescription, Card, CardContent, CardHeader, CardTitle, Markdown } from '@/shared/ui'

import { unsourcedCount, type Source, type Work } from './model'

/** Every source with the exact quotes taken from it (the evidence chain:
 *  works → work_sources → quotes). */
function Evidence({ sources }: { sources: Source[] }) {
  const { t } = useTranslation()
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('work.evidence')}</CardTitle>
      </CardHeader>
      <CardContent>
        {sources.length === 0 && <p className="text-muted-foreground">{t('work.noSources')}</p>}
        <ol className="grid gap-4">
          {sources.map((source) => (
            <li key={source.id} className="grid gap-2">
              <div className="grid">
                {source.kind === 'web' ? (
                  <a
                    href={source.location}
                    target="_blank"
                    rel="noopener noreferrer nofollow"
                    className="font-medium text-primary underline underline-offset-2"
                  >
                    {source.title}
                  </a>
                ) : (
                  <span className="font-medium">{source.title}</span>
                )}
                <span className="text-xs break-all text-muted-foreground">
                  {source.location} · {t('work.accessed', { date: formatDateTime(source.accessed_at) })}
                </span>
              </div>
              <ul className="grid gap-2">
                {source.quotes.map((quote) => (
                  <li key={quote.id} className="grid gap-1 border-l-2 border-primary/40 pl-3">
                    <span className="text-sm">{quote.claim}</span>
                    <q className="text-sm text-muted-foreground italic">{quote.quote}</q>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  )
}

/** The text of a work, a warning about sentences without a source, and
 *  the evidence. */
export function WorkView({ work }: { work: Work }) {
  const { t } = useTranslation()
  const unsourced = unsourcedCount(work.text)
  return (
    <div className="grid gap-4">
      {unsourced > 0 && (
        <Alert variant="destructive">
          <AlertDescription>{t('work.unsourced', { count: unsourced })}</AlertDescription>
        </Alert>
      )}
      <Card>
        <CardContent className="grid gap-2">
          <p className="text-xs text-muted-foreground">{t('work.updated', { date: formatDateTime(work.updated_at) })}</p>
          <Markdown text={work.text} />
        </CardContent>
      </Card>
      <Evidence sources={work.sources} />
    </div>
  )
}
