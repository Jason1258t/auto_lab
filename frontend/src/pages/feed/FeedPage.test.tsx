// Publish a work, the public feed, a publication and a publisher page.
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import type { PublicationDetail } from '@/entities/publication'
import type { TaskDetail } from '@/entities/task'
import type { Work } from '@/entities/work'
import type { Workspace } from '@/entities/workspace'
import { API, server, signedIn } from '@/test/server'
import { renderApp } from '@/test/render'

const PUBLISHER = { id: 4, name: 'Sky Lab', description: 'Notes about the sky.', created_at: '2026-10-07T10:00:00Z' }
const DETAIL: PublicationDetail = {
  id: 3,
  title: 'Why is the sky blue?',
  description: 'A short answer.',
  published_at: '2026-10-07T12:00:00Z',
  publisher: PUBLISHER,
  text: '# Why is the sky blue?\n\nShort waves scatter more [1]. *(⚠ no source)*',
  sources: [],
}
const OWNED: Workspace = {
  id: 7,
  name: 'Sky research',
  description: null,
  visibility: 'private',
  owner_id: 1,
  owner_username: 'ann',
  owner_display_name: 'Ann',
  archived_at: null,
  created_at: '2026-10-07T10:00:00Z',
  is_owner: true,
  my_roles: [],
}
const DONE: TaskDetail = {
  id: 11,
  workspace_id: 7,
  title: 'Why is the sky blue?',
  input: 'Explain it.',
  status: 'done',
  pipeline_name: 'research',
  pipeline_version: '1.0.0',
  pipeline_version_id: 1,
  model_id: 1,
  created_by: 1,
  reviewer_id: 1,
  created_at: '2026-10-07T10:00:00Z',
  started_at: null,
  finished_at: null,
  plan: [],
  steps: [],
}
const WORK: Work = { task_id: 11, workspace_id: 7, title: DONE.title, task_status: 'done', summary: null, text: DETAIL.text, updated_at: '2026-10-07T11:00:00Z', sources: [] }

function doneTask(workspace: Workspace = OWNED) {
  return [
    ...signedIn,
    http.get(`${API}/tasks/11`, () => HttpResponse.json(DONE)),
    http.get(`${API}/tasks/11/calls`, () => HttpResponse.json([])),
    http.get(`${API}/tasks/11/reviews`, () => HttpResponse.json([])),
    http.get(`${API}/tasks/11/work`, () => HttpResponse.json(WORK)),
    http.get(`${API}/workspaces/7`, () => HttpResponse.json(workspace)),
    http.get(`${API}/workspaces/7/members`, () => HttpResponse.json([])),
  ]
}

test('a first-time owner creates a publisher and publishes in one dialog', async () => {
  const calls: string[] = []
  server.use(
    ...doneTask(),
    http.get(`${API}/publishers/mine`, () => HttpResponse.json([])),
    http.post(`${API}/publishers`, async ({ request }) => {
      calls.push(`publisher ${JSON.stringify(await request.json())}`)
      return HttpResponse.json(PUBLISHER, { status: 201 })
    }),
    http.post(`${API}/publications`, async ({ request }) => {
      calls.push(`publication ${JSON.stringify(await request.json())}`)
      return HttpResponse.json({ ...DETAIL, text: undefined, sources: undefined }, { status: 201 })
    }),
    http.get(`${API}/publications/3`, () => HttpResponse.json(DETAIL)),
  )
  renderApp('/tasks/11')
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Publish' }))
  const dialog = await screen.findByRole('dialog')
  await user.type(await within(dialog).findByLabelText('Publisher name'), 'Sky Lab')
  expect(within(dialog).getByLabelText('Title')).toHaveValue('Why is the sky blue?')
  await user.click(within(dialog).getByRole('button', { name: 'Publish' }))

  expect(await screen.findByText('A short answer.')).toBeInTheDocument()
  expect(calls).toEqual([
    'publisher {"name":"Sky Lab"}',
    'publication {"task_id":11,"publisher_id":4,"title":"Why is the sky blue?","description":null}',
  ])
  // A publication keeps the marks, but has no reviewer warning.
  expect(screen.getByText('(⚠ no source)')).toBeInTheDocument()
  expect(screen.queryByText(/Check it before you accept/)).not.toBeInTheDocument()
})

test('only the owner sees Publish', async () => {
  server.use(...doneTask({ ...OWNED, owner_id: 9, is_owner: false, my_roles: ['editor', 'member'] }))
  renderApp('/tasks/11')
  expect(await screen.findByText('Sources and quotes')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Publish' })).not.toBeInTheDocument()
})

test('anyone reads the feed and a publisher page without login', async () => {
  const listed = { id: 3, title: DETAIL.title, description: DETAIL.description, published_at: DETAIL.published_at, publisher: PUBLISHER }
  const asked: (string | null)[] = []
  server.use(
    http.get(`${API}/publications`, ({ request }) => {
      asked.push(new URL(request.url).searchParams.get('publisher_id'))
      return HttpResponse.json([listed])
    }),
    http.get(`${API}/publishers/4`, () => HttpResponse.json(PUBLISHER)),
  )
  renderApp('/feed')
  const user = userEvent.setup()
  expect(await screen.findByRole('link', { name: 'Why is the sky blue?' })).toHaveAttribute('href', '/publications/3')
  await user.click(screen.getByRole('link', { name: 'Sky Lab' }))
  expect(await screen.findByText('Notes about the sky.')).toBeInTheDocument()
  expect(asked).toEqual([null, '4'])
})
