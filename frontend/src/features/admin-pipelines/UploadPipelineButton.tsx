// Upload a pipeline YAML file: a new version of a pipeline, or a new
// pipeline. "Check" validates it without saving. The name and version
// fields decide; the backend sets the file's own lines to them.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { adminKeys, type AdminPipeline } from '@/entities/admin'
import { api, call, errorText } from '@/shared/api'
import {
  Alert,
  AlertDescription,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  FormField,
  Input,
  Label,
  SelectField,
} from '@/shared/ui'

type Mode = 'version' | 'new'

/** The next minor version: 1.2.0 -> 1.3.0. */
export function nextVersion(version: string | undefined): string {
  const match = /^(\d+)\.(\d+)\.(\d+)$/.exec(version ?? '')
  return match ? `${match[1]}.${Number(match[2]) + 1}.0` : '1.0.0'
}

function UploadForm({ pipelines, onDone }: { pipelines: AdminPipeline[]; onDone: () => void }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const first = pipelines[0]
  const [mode, setMode] = useState<Mode>(first ? 'version' : 'new')
  const [pipelineId, setPipelineId] = useState(String(first?.id ?? ''))
  const [name, setName] = useState(first?.name ?? '')
  const [version, setVersion] = useState(nextVersion(first?.versions[0]?.version_name))
  const [file, setFile] = useState<File | null>(null)

  // The newest existing version of the chosen pipeline (shown as a hint).
  const newest = mode === 'version' ? pipelines.find((p) => String(p.id) === pipelineId)?.versions[0]?.version_name : undefined

  const pick = (id: string) => {
    const pipeline = pipelines.find((p) => String(p.id) === id)
    setPipelineId(id)
    setName(pipeline?.name ?? '')
    setVersion(nextVersion(pipeline?.versions[0]?.version_name))
  }
  const switchMode = (next: string) => {
    setMode(next as Mode)
    if (next === 'new') {
      setName('')
      setVersion('1.0.0')
    } else {
      pick(pipelineId || String(first?.id ?? ''))
    }
  }

  const mutation = useMutation({
    mutationFn: (dryRun: boolean) => {
      const form = new FormData()
      form.append('file', file as File)
      form.append('name', name)
      form.append('version', version)
      form.append('dry_run', String(dryRun))
      return call(
        api.POST('/api/v1/admin/pipelines/upload', { body: {} as never, bodySerializer: () => form }),
      )
    },
    onSuccess: async (result) => {
      if (!result.saved) return
      await queryClient.invalidateQueries({ queryKey: adminKeys.pipelines })
      await queryClient.invalidateQueries({ queryKey: ['catalog', 'pipelines'] })
    },
  })
  const submit = (dryRun: boolean) => (event?: FormEvent) => {
    event?.preventDefault()
    mutation.mutate(dryRun)
  }
  const result = mutation.data
  return (
    <form onSubmit={submit(false)} className="grid gap-4">
      <DialogHeader>
        <DialogTitle>{t('pipelines.upload')}</DialogTitle>
        <DialogDescription>{t('pipelines.uploadText')}</DialogDescription>
      </DialogHeader>
      <SelectField
        id="pipeline-mode"
        label={t('pipelines.mode')}
        value={mode}
        onChange={switchMode}
        options={[
          ...(pipelines.length ? [{ value: 'version', label: t('pipelines.modeVersion') }] : []),
          { value: 'new', label: t('pipelines.modeNew') },
        ]}
      />
      {mode === 'version' && (
        <SelectField
          id="pipeline-existing"
          label={t('pipelines.pipeline')}
          value={pipelineId}
          onChange={pick}
          options={pipelines.map((p) => ({
            value: String(p.id),
            label: `${p.name}${p.versions[0] ? ` (${p.versions[0].version_name})` : ''}`,
          }))}
        />
      )}
      <FormField id="pipeline-name" label={t('pipelines.name')} hint={t('pipelines.nameHint')} value={name} onChange={setName} maxLength={50} />
      <FormField
        id="pipeline-version"
        label={t('pipelines.version')}
        hint={newest ? t('pipelines.versionHintNewest', { newest }) : t('pipelines.versionHint')}
        value={version}
        onChange={setVersion}
        maxLength={20}
      />
      <div className="grid gap-2">
        <Label htmlFor="pipeline-file">{t('pipelines.file')}</Label>
        <Input
          id="pipeline-file"
          type="file"
          accept=".yaml,.yml,text/yaml"
          onChange={(e) => {
            setFile(e.target.files?.[0] ?? null)
            mutation.reset()
          }}
        />
      </div>
      {mutation.isError && (
        <Alert variant="destructive">
          <AlertDescription className="whitespace-pre-wrap break-words">
            {errorText(mutation.error).replaceAll('; ', '\n')}
          </AlertDescription>
        </Alert>
      )}
      {result && (
        <Alert>
          <AlertDescription className="grid gap-1">
            <span>
              {result.saved
                ? t(result.created_pipeline ? 'pipelines.savedNew' : 'pipelines.saved', { name: result.name, version: result.version_name })
                : t('pipelines.valid')}
            </span>
            {result.notes.map((note) => (
              <span key={note} className="text-muted-foreground">
                {note}
              </span>
            ))}
          </AlertDescription>
        </Alert>
      )}
      <DialogFooter>
        {result?.saved ? (
          <Button type="button" onClick={onDone}>
            {t('common.done')}
          </Button>
        ) : (
          <>
            <Button type="button" variant="outline" disabled={!file || mutation.isPending} onClick={() => submit(true)()}>
              {t('pipelines.check')}
            </Button>
            <Button type="submit" disabled={!file || mutation.isPending}>
              {t('pipelines.uploadButton')}
            </Button>
          </>
        )}
      </DialogFooter>
    </form>
  )
}

export function UploadPipelineButton({ pipelines }: { pipelines: AdminPipeline[] }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button>{t('pipelines.upload')}</Button>} />
      <DialogContent className="sm:max-w-lg">{open && <UploadForm pipelines={pipelines} onDone={() => setOpen(false)} />}</DialogContent>
    </Dialog>
  )
}
