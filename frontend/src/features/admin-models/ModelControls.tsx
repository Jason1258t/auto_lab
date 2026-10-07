// Add a model to the catalog, and switch a model on or off for new tasks.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { adminKeys, type AdminModel, type Provider } from '@/entities/admin'
import { api, call, errorText } from '@/shared/api'
import {
  Button,
  Checkbox,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  FormError,
  FormField,
  SelectField,
} from '@/shared/ui'

/** New tasks may use only available models (GET /models). */
export function AvailableCheckbox({ model }: { model: AdminModel }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: (available: boolean) =>
      call(
        api.PATCH('/api/v1/admin/models/{model_id}', {
          params: { path: { model_id: model.id } },
          body: { available },
        }),
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: adminKeys.models })
      await queryClient.invalidateQueries({ queryKey: ['catalog', 'models'] })
    },
  })
  const id = `model-available-${model.id}`
  return (
    <span className="flex items-center gap-2">
      <Checkbox id={id} checked={model.available} disabled={mutation.isPending} onCheckedChange={(v) => mutation.mutate(v)} />
      <label htmlFor={id} className="text-sm">
        {t('admin.available')}
      </label>
      {mutation.isError && (
        <span role="alert" className="text-xs text-destructive">
          {errorText(mutation.error)}
        </span>
      )}
    </span>
  )
}

/** Empty text = not set; otherwise a whole number. */
function optionalInt(text: string): number | null {
  return text.trim() === '' ? null : Number(text)
}

function AddModelForm({ providers, onDone }: { providers: Provider[]; onDone: () => void }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [values, setValues] = useState({
    provider: String(providers[0]?.id ?? ''),
    name: '',
    context: '4096',
    vram: '',
    description: '',
  })
  const set = (key: keyof typeof values) => (value: string) => setValues((v) => ({ ...v, [key]: value }))
  const mutation = useMutation({
    mutationFn: () =>
      call(
        api.POST('/api/v1/admin/models', {
          body: {
            provider_id: Number(values.provider),
            name: values.name.trim(),
            context_length: Number(values.context),
            vram_mb: optionalInt(values.vram),
            description: values.description.trim() || null,
          },
        }),
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: adminKeys.models })
      await queryClient.invalidateQueries({ queryKey: ['catalog', 'models'] })
      onDone()
    },
  })
  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    mutation.mutate()
  }
  return (
    <form onSubmit={onSubmit} className="grid gap-4">
      <DialogHeader>
        <DialogTitle>{t('admin.addModel')}</DialogTitle>
      </DialogHeader>
      <SelectField
        id="model-provider"
        label={t('admin.provider')}
        value={values.provider}
        onChange={set('provider')}
        options={providers.map((p) => ({ value: String(p.id), label: `${p.name} (${p.adapter})` }))}
      />
      <FormField id="model-name" label={t('admin.modelName')} hint={t('admin.modelNameHint')} value={values.name} onChange={set('name')} maxLength={200} />
      <FormField id="model-context" label={t('admin.context')} type="number" value={values.context} onChange={set('context')} />
      <FormField id="model-vram" label={t('admin.vram')} type="number" value={values.vram} onChange={set('vram')} required={false} />
      <FormField id="model-description" label={t('workspace.description')} value={values.description} onChange={set('description')} multiline required={false} />
      <FormError error={mutation.isError ? errorText(mutation.error) : null} />
      <DialogFooter>
        <Button type="submit" disabled={mutation.isPending || !providers.length}>
          {t('admin.addModel')}
        </Button>
      </DialogFooter>
    </form>
  )
}

export function AddModelButton({ providers }: { providers: Provider[] }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button>{t('admin.addModel')}</Button>} />
      <DialogContent className="sm:max-w-lg">{open && <AddModelForm providers={providers} onDone={() => setOpen(false)} />}</DialogContent>
    </Dialog>
  )
}
