// Add a model to the catalog, edit it (token budget profile too), and
// switch a model on or off for new tasks.
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

const SIZE_CLASSES = ['small', 'medium', 'large', 'small_think', 'medium_think', 'large_think'] as const
type SizeClass = (typeof SIZE_CLASSES)[number]

/** Add a model (no `model`) or edit one. The provider is set only once. */
function ModelForm({ providers, model, onDone }: { providers: Provider[]; model?: AdminModel; onDone: () => void }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const text = (n: number | null | undefined) => (n == null ? '' : String(n))
  const [values, setValues] = useState({
    provider: String(model?.provider_id ?? providers[0]?.id ?? ''),
    name: model?.name ?? '',
    context: String(model?.context_length ?? 4096),
    vram: text(model?.vram_mb),
    sizeClass: (model?.size_class ?? 'small') as SizeClass,
    reasoning: text(model?.reasoning_tokens),
    maxOutput: text(model?.max_output_tokens),
    description: model?.description ?? '',
  })
  const set = (key: keyof typeof values) => (value: string) => setValues((v) => ({ ...v, [key]: value }))
  const thinks = values.sizeClass.endsWith('_think')
  const fields = () => ({
    name: values.name.trim(),
    context_length: Number(values.context),
    vram_mb: optionalInt(values.vram),
    size_class: values.sizeClass,
    reasoning_tokens: thinks ? optionalInt(values.reasoning) : null,
    max_output_tokens: optionalInt(values.maxOutput),
    description: values.description.trim() || null,
  })
  const mutation = useMutation({
    mutationFn: () =>
      model
        ? call(
            api.PATCH('/api/v1/admin/models/{model_id}', {
              params: { path: { model_id: model.id } },
              body: fields(),
            }),
          )
        : call(api.POST('/api/v1/admin/models', { body: { provider_id: Number(values.provider), ...fields() } })),
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
  const title = model ? t('admin.editModel') : t('admin.addModel')
  return (
    <form onSubmit={onSubmit} className="grid gap-4">
      <DialogHeader>
        <DialogTitle>{title}</DialogTitle>
      </DialogHeader>
      {!model && (
        <SelectField
          id="model-provider"
          label={t('admin.provider')}
          value={values.provider}
          onChange={set('provider')}
          options={providers.map((p) => ({ value: String(p.id), label: `${p.name} (${p.adapter})` }))}
        />
      )}
      <FormField id="model-name" label={t('admin.modelName')} hint={t('admin.modelNameHint')} value={values.name} onChange={set('name')} maxLength={200} />
      <FormField id="model-context" label={t('admin.context')} type="number" value={values.context} onChange={set('context')} />
      <FormField id="model-vram" label={t('admin.vram')} type="number" value={values.vram} onChange={set('vram')} required={false} />
      <SelectField
        id="model-size-class"
        label={t('admin.sizeClass')}
        hint={t('admin.sizeClassHint')}
        value={values.sizeClass}
        onChange={set('sizeClass')}
        options={SIZE_CLASSES.map((c) => ({ value: c, label: t(`admin.sizeClasses.${c}`) }))}
      />
      {thinks && (
        <FormField
          id="model-reasoning"
          label={t('admin.reasoningTokens')}
          hint={t('admin.reasoningTokensHint')}
          type="number"
          value={values.reasoning}
          onChange={set('reasoning')}
          required={false}
        />
      )}
      <FormField
        id="model-max-output"
        label={t('admin.maxOutputTokens')}
        hint={t('admin.maxOutputTokensHint')}
        type="number"
        value={values.maxOutput}
        onChange={set('maxOutput')}
        required={false}
      />
      <FormField id="model-description" label={t('workspace.description')} value={values.description} onChange={set('description')} multiline required={false} />
      <FormError error={mutation.isError ? errorText(mutation.error) : null} />
      <DialogFooter>
        <Button type="submit" disabled={mutation.isPending || (!model && !providers.length)}>
          {model ? t('workspace.save') : t('admin.addModel')}
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
      <DialogContent className="sm:max-w-lg">{open && <ModelForm providers={providers} onDone={() => setOpen(false)} />}</DialogContent>
    </Dialog>
  )
}

export function EditModelButton({ model }: { model: AdminModel }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button variant="outline" size="sm" aria-label={t('admin.editModelOf', { name: model.name })}>
            {t('workspace.edit')}
          </Button>
        }
      />
      <DialogContent className="sm:max-w-lg">{open && <ModelForm providers={[]} model={model} onDone={() => setOpen(false)} />}</DialogContent>
    </Dialog>
  )
}
