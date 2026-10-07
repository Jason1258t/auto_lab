// Add a model provider (where models run: Ollama today; OpenAI-compatible
// and Anthropic later, see ARCHITECTURE.md "gateway").
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { adminKeys } from '@/entities/admin'
import { api, call, errorText } from '@/shared/api'
import {
  Button,
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

const ADAPTERS = ['ollama', 'openai_compatible', 'anthropic'] as const

function AddProviderForm({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [values, setValues] = useState({ name: '', adapter: 'ollama', baseUrl: '', secretId: '' })
  const set = (key: keyof typeof values) => (value: string) => setValues((v) => ({ ...v, [key]: value }))
  const mutation = useMutation({
    mutationFn: () =>
      call(
        api.POST('/api/v1/admin/model-providers', {
          body: {
            name: values.name.trim(),
            adapter: values.adapter as (typeof ADAPTERS)[number],
            base_url: values.baseUrl.trim() || null,
            secret_id: values.secretId.trim() || null,
          },
        }),
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: adminKeys.providers })
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
        <DialogTitle>{t('admin.addProvider')}</DialogTitle>
      </DialogHeader>
      <FormField id="provider-name" label={t('admin.providerName')} value={values.name} onChange={set('name')} maxLength={100} />
      <SelectField
        id="provider-adapter"
        label={t('admin.adapter')}
        hint={t('admin.adapterHint')}
        value={values.adapter}
        onChange={set('adapter')}
        options={ADAPTERS.map((a) => ({ value: a, label: a }))}
      />
      <FormField id="provider-url" label={t('admin.baseUrl')} hint={t('admin.baseUrlHint')} value={values.baseUrl} onChange={set('baseUrl')} required={false} />
      <FormField id="provider-secret" label={t('admin.secretId')} hint={t('admin.secretIdHint')} value={values.secretId} onChange={set('secretId')} required={false} />
      <FormError error={mutation.isError ? errorText(mutation.error) : null} />
      <DialogFooter>
        <Button type="submit" disabled={mutation.isPending}>
          {t('admin.addProvider')}
        </Button>
      </DialogFooter>
    </form>
  )
}

export function AddProviderButton() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button>{t('admin.addProvider')}</Button>} />
      <DialogContent className="sm:max-w-lg">{open && <AddProviderForm onDone={() => setOpen(false)} />}</DialogContent>
    </Dialog>
  )
}
