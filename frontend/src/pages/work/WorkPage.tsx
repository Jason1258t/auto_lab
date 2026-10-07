// A work on its own page: for members, and for anyone when the workspace
// is public and the work is accepted.
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'

import { useWork, WorkView } from '@/entities/work'
import { errorText } from '@/shared/api'
import { FormError } from '@/shared/ui'

export function WorkPage() {
  const { t } = useTranslation()
  const taskId = Number(useParams().taskId)
  const work = useWork(taskId)
  return (
    <section className="grid gap-6">
      {work.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
      {work.isError && <FormError error={errorText(work.error)} />}
      {work.data === null && <p className="text-muted-foreground">{t('work.notFound')}</p>}
      {work.data && (
        <>
          <Link to={`/workspaces/${work.data.workspace_id}`} className="text-sm text-muted-foreground hover:text-foreground">
            ← {t('work.backToWorkspace')}
          </Link>
          <header className="grid gap-1">
            <h1 className="font-heading text-3xl font-semibold">{work.data.title}</h1>
            {work.data.summary && <p className="text-muted-foreground">{work.data.summary}</p>}
          </header>
          <WorkView work={work.data} />
        </>
      )}
    </section>
  )
}
