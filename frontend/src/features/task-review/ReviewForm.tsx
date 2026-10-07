// Accept the work, or reject it with a comment. A rejection sends the
// task back to the worker: it runs again from `rerun_from` with the
// comment in the prompt.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { reviewKeys } from '@/entities/review'
import { taskKeys, type TaskDetail } from '@/entities/task'
import { workKeys } from '@/entities/work'
import { api, call, errorText } from '@/shared/api'
import { Button, FormError, Label, Textarea } from '@/shared/ui'

export function ReviewForm({ task }: { task: TaskDetail }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [comment, setComment] = useState('')
  const mutation = useMutation({
    mutationFn: (result: 'accepted' | 'rejected') =>
      call(
        api.POST('/api/v1/tasks/{task_id}/reviews', {
          params: { path: { task_id: task.id } },
          body: { result, comment: comment.trim() || null },
        }),
      ),
    onSuccess: async () => {
      setComment('')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: taskKeys.detail(task.id) }),
        queryClient.invalidateQueries({ queryKey: reviewKeys.list(task.id) }),
        queryClient.invalidateQueries({ queryKey: workKeys.one(task.id) }),
        queryClient.invalidateQueries({ queryKey: taskKeys.list(task.workspace_id) }),
      ])
    },
  })
  const noComment = comment.trim() === ''
  return (
    <div className="grid gap-3">
      <div className="grid gap-2">
        <Label htmlFor="review-comment">{t('review.comment')}</Label>
        <Textarea
          id="review-comment"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          maxLength={5000}
          aria-describedby="review-comment-hint"
        />
        <p id="review-comment-hint" className="text-xs text-muted-foreground">
          {t('review.commentHint')}
        </p>
      </div>
      <FormError error={mutation.isError ? errorText(mutation.error) : null} />
      <div className="flex flex-wrap gap-2">
        <Button disabled={mutation.isPending} onClick={() => mutation.mutate('accepted')}>
          {t('review.accept')}
        </Button>
        <Button variant="destructive" disabled={mutation.isPending || noComment} onClick={() => mutation.mutate('rejected')}>
          {t('review.reject')}
        </Button>
      </div>
    </div>
  )
}
