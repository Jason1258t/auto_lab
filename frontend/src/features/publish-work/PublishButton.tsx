// Publish an accepted work to the public feed, under one of my
// publishers. A first-time user creates the publisher in the same dialog.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'

import { publicationKeys, useMyPublishers } from '@/entities/publication'
import type { TaskDetail } from '@/entities/task'
import { api, call, errorText } from '@/shared/api'
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  FormError,
  FormField,
  SelectField,
} from '@/shared/ui'

const NEW = 'new'

function PublishForm({ task }: { task: TaskDetail }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const publishers = useMyPublishers()
  const [choice, setChoice] = useState('')
  const [publisherName, setPublisherName] = useState('')
  const [title, setTitle] = useState(task.title)
  const [description, setDescription] = useState('')

  const options = [
    ...(publishers.data ?? []).map((p) => ({ value: String(p.id), label: p.name })),
    { value: NEW, label: t('publish.newPublisher') },
  ]
  // Default: my first publisher, or "new" if I have none yet.
  const selected = choice || (publishers.data?.length ? String(publishers.data[0].id) : NEW)

  const mutation = useMutation({
    mutationFn: async () => {
      let publisherId = Number(selected)
      if (selected === NEW) {
        const created = await call(api.POST('/api/v1/publishers', { body: { name: publisherName.trim() } }))
        publisherId = created.id
        await queryClient.invalidateQueries({ queryKey: publicationKeys.myPublishers })
        setChoice(String(created.id)) // if publishing fails now, do not create it twice
      }
      return call(
        api.POST('/api/v1/publications', {
          body: {
            task_id: task.id,
            publisher_id: publisherId,
            title: title.trim(),
            description: description.trim() || null,
          },
        }),
      )
    },
    onSuccess: async (publication) => {
      await queryClient.invalidateQueries({ queryKey: ['publications'] })
      void navigate(`/publications/${publication.id}`)
    },
  })
  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    mutation.mutate()
  }
  return (
    <form onSubmit={onSubmit} className="grid gap-4">
      <DialogHeader>
        <DialogTitle>{t('publish.title')}</DialogTitle>
        <DialogDescription>{t('publish.text')}</DialogDescription>
      </DialogHeader>
      <SelectField id="publish-publisher" label={t('publish.publisher')} value={selected} onChange={setChoice} options={options} />
      {selected === NEW && (
        <FormField
          id="publish-publisher-name"
          label={t('publish.publisherName')}
          hint={t('publish.publisherHint')}
          value={publisherName}
          onChange={setPublisherName}
          maxLength={100}
        />
      )}
      <FormField id="publish-title" label={t('task.titleField')} value={title} onChange={setTitle} maxLength={300} />
      <FormField
        id="publish-description"
        label={t('workspace.description')}
        value={description}
        onChange={setDescription}
        maxLength={5000}
        multiline
        required={false}
      />
      <FormError error={mutation.isError ? errorText(mutation.error) : null} />
      <DialogFooter>
        <Button type="submit" disabled={mutation.isPending || publishers.isPending}>
          {t('publish.submit')}
        </Button>
      </DialogFooter>
    </form>
  )
}

export function PublishButton({ task }: { task: TaskDetail }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="outline">{t('publish.button')}</Button>} />
      <DialogContent className="sm:max-w-lg">{open && <PublishForm task={task} />}</DialogContent>
    </Dialog>
  )
}
