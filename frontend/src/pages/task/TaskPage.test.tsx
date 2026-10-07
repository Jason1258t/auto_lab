// New task and the task page, through the whole app with a fake backend.
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import type { CallLog, LlmCall } from '@/entities/call'
import type { TaskDetail } from '@/entities/task'
import type { Workspace } from '@/entities/workspace'
import { API, apiError, server, signedIn } from '@/test/server'
import { renderApp } from '@/test/render'

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
const PLAN = [
  { step_id: 'plan', kind: 'plan' },
  { step_id: 'search', kind: 'web_search' },
  { step_id: 'write', kind: 'write' },
]
const DRAFT: TaskDetail = {
  id: 11,
  workspace_id: 7,
  title: 'Why is the sky blue?',
  input: 'Explain Rayleigh scattering.',
  status: 'draft',
  pipeline_name: 'research',
  pipeline_version: '1.0.0',
  pipeline_version_id: 1,
  model_id: 1,
  created_by: 1,
  reviewer_id: 1,
  created_at: '2026-10-07T10:00:00Z',
  started_at: null,
  finished_at: null,
  plan: PLAN,
  steps: [],
}
const step = (index: number, id: string, status: 'pending' | 'running' | 'done', review_id: number | null = null) => ({
  step_index: index,
  step_id: id,
  kind: id,
  status,
  summary: status === 'done' ? `${id} finished` : null,
  review_id,
  started_at: status === 'pending' ? null : '2026-10-07T10:00:00Z',
  finished_at: status === 'done' ? '2026-10-07T10:00:04Z' : null,
})

function taskAnswers(task: () => TaskDetail, workspace: Workspace = OWNED, calls: LlmCall[] = []) {
  return [
    ...signedIn,
    http.get(`${API}/tasks/11`, () => HttpResponse.json(task())),
    http.get(`${API}/tasks/11/calls`, () => HttpResponse.json(calls)),
    http.get(`${API}/workspaces/7`, () => HttpResponse.json(workspace)),
  ]
}

const CALL: LlmCall = {
  id: 31,
  step_index: 0,
  attempt: 1,
  status: 'done',
  error: null,
  created_at: '2026-10-07T10:00:00Z',
  started_at: '2026-10-07T10:00:00Z',
  finished_at: '2026-10-07T10:00:03.500Z',
  input_tokens: 120,
  output_tokens: 30,
  finish_reason: 'stop',
  valid_json: true,
}
const LOG: CallLog = {
  request: {
    model: 'qwen2.5:3b',
    messages: [
      { role: 'system', content: 'You plan web research. Reply with JSON only.' },
      { role: 'user', content: 'Research task: <b>sky</b>' },
    ],
    schema: { type: 'object', required: ['queries'] },
    params: {},
  },
  response: { text: '{"queries":["why sky blue"]}', raw: null },
  created_at: '2026-10-07T10:00:00Z',
  answered_at: '2026-10-07T10:00:03Z',
}

test('a new task is created as a draft and opens its page', async () => {
  let sent: unknown = null
  server.use(
    ...taskAnswers(() => DRAFT),
    http.get(`${API}/workspaces/7/tasks`, () => HttpResponse.json([])),
    http.get(`${API}/workspaces/7/members`, () =>
      HttpResponse.json([{ user_id: 2, username: 'bob', display_name: 'Bob', roles: ['member'] }]),
    ),
    http.get(`${API}/pipelines`, () =>
      HttpResponse.json([
        { id: 1, name: 'research', description: null, version_id: 1, version_name: '1.0.0' },
        { id: 2, name: 'study_notes', description: null, version_id: null, version_name: null },
      ]),
    ),
    http.get(`${API}/models`, () =>
      HttpResponse.json([
        { id: 1, provider_id: 1, name: 'qwen2.5:3b', context_length: 4096, vram_mb: null, ram_mb: null, cost_per_1m_input: null, cost_per_1m_output: null, description: null, available: true, created_at: '2026-10-07T10:00:00Z' },
        { id: 2, provider_id: 1, name: 'off-model', context_length: 4096, vram_mb: null, ram_mb: null, cost_per_1m_input: null, cost_per_1m_output: null, description: null, available: false, created_at: '2026-10-07T10:00:00Z' },
      ]),
    ),
    http.post(`${API}/workspaces/7/tasks`, async ({ request }) => {
      sent = await request.json()
      return HttpResponse.json(DRAFT, { status: 201 })
    }),
  )
  renderApp('/workspaces/7')
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'New task' }))
  const dialog = await screen.findByRole('dialog')
  await user.type(within(dialog).getByLabelText('Title'), 'Why is the sky blue?')
  await user.type(within(dialog).getByLabelText('Task'), 'Explain Rayleigh scattering.')
  // Pipelines without a version and unavailable models are not offered.
  expect(within(dialog).getAllByRole('option').map((o) => o.textContent)).toEqual([
    'research 1.0.0',
    'qwen2.5:3b',
    'Me',
    'Bob',
  ])
  await user.selectOptions(within(dialog).getByLabelText('Reviewer'), 'Bob')
  await user.click(within(dialog).getByRole('button', { name: 'New task' }))

  expect(await screen.findByText('This is a draft. Nothing runs until you queue it.')).toBeInTheDocument()
  expect(sent).toEqual({
    title: 'Why is the sky blue?',
    input: 'Explain Rayleigh scattering.',
    pipeline_id: 1,
    model_id: 1,
    reviewer_id: 2,
  })
})

test('a draft shows the planned steps and can be queued', async () => {
  let current = DRAFT
  server.use(
    ...taskAnswers(() => current),
    http.post(`${API}/tasks/11/queue`, () => {
      current = { ...DRAFT, status: 'queued' }
      return HttpResponse.json(current)
    }),
  )
  renderApp('/tasks/11')
  const user = userEvent.setup()
  expect(await screen.findByText('web_search')).toBeInTheDocument()
  expect(screen.getAllByLabelText('Waiting')).toHaveLength(3)
  await user.click(await screen.findByRole('button', { name: 'Queue' }))
  expect(await screen.findByText('Queued')).toBeInTheDocument()
  expect(screen.getByText('Updating…')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
})

test('a running task shows each step, and a revision after a review', async () => {
  const running: TaskDetail = {
    ...DRAFT,
    status: 'running',
    steps: [step(0, 'plan', 'done'), step(1, 'search', 'done'), step(2, 'write', 'done'), step(3, 'write', 'running', 5)],
  }
  server.use(...taskAnswers(() => running))
  renderApp('/tasks/11')
  expect(await screen.findByText('search finished')).toBeInTheDocument()
  expect(screen.getAllByText('4 seconds')).toHaveLength(3)
  expect(screen.getByText('Revision after a rejected review')).toBeInTheDocument()
  expect(screen.getByLabelText('Running')).toBeInTheDocument()
})

test('a member sees the task but no buttons', async () => {
  const member: Workspace = { ...OWNED, owner_id: 9, is_owner: false, my_roles: ['member'] }
  server.use(...taskAnswers(() => DRAFT, member))
  renderApp('/tasks/11')
  expect(await screen.findByRole('heading', { name: 'Why is the sky blue?' })).toBeInTheDocument()
  expect(await screen.findByText('← Sky research')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Queue' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
})

test('delete asks first and goes back to the workspace', async () => {
  server.use(
    ...taskAnswers(() => DRAFT),
    http.delete(`${API}/tasks/11`, () => new HttpResponse(null, { status: 204 })),
    http.get(`${API}/workspaces/7/tasks`, () => HttpResponse.json([])),
  )
  renderApp('/tasks/11')
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Delete' }))
  await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Delete' }))
  expect(await screen.findByText('No tasks yet.')).toBeInTheDocument()
})

test('an unknown task shows a clear message', async () => {
  server.use(...signedIn, http.get(`${API}/tasks/404`, () => apiError(404, 'task_not_found', 'Task 404 not found')))
  renderApp('/tasks/404')
  expect(await screen.findByText('This task does not exist, or you have no access to it.')).toBeInTheDocument()
})

test('each step lists its model calls; a call opens its full prompt and answer', async () => {
  const done: TaskDetail = { ...DRAFT, status: 'in_review', steps: [step(0, 'plan', 'done'), step(1, 'search', 'done'), step(2, 'write', 'done')] }
  const failed: LlmCall = { ...CALL, id: 32, step_index: 2, attempt: 2, status: 'failed', error: 'The model did not answer', input_tokens: null, output_tokens: null, valid_json: null, finish_reason: null }
  let logRequests = 0
  server.use(
    ...taskAnswers(() => done, OWNED, [CALL, failed]),
    http.get(`${API}/calls/31/log`, () => {
      logRequests += 1
      return HttpResponse.json(LOG)
    }),
  )
  renderApp('/tasks/11')
  const user = userEvent.setup()
  const call = await screen.findByRole('button', { name: /Model call 31/ })
  expect(call).toHaveTextContent('120 → 30 tokens · 3.5 s')
  expect(screen.getByText('The model did not answer')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Model call 32/ })).toHaveTextContent('attempt 2')
  expect(logRequests).toBe(0) // the log loads only when opened

  await user.click(call)
  expect(await screen.findByText('You plan web research. Reply with JSON only.')).toBeInTheDocument()
  // Web text is shown as text, never as HTML.
  expect(screen.getByText('Research task: <b>sky</b>')).toBeInTheDocument()
  expect(screen.getByText(/"why sky blue"/)).toBeInTheDocument()
  expect(screen.getByText('Expected JSON shape')).toBeInTheDocument()

  await user.click(call) // close and open again: no second request
  await user.click(call)
  expect(logRequests).toBe(1)
})

test('a deleted log shows a clear message', async () => {
  const done: TaskDetail = { ...DRAFT, status: 'done', steps: [step(0, 'plan', 'done')] }
  server.use(
    ...taskAnswers(() => done, OWNED, [CALL]),
    http.get(`${API}/calls/31/log`, () => apiError(404, 'log_not_found', 'No log for call 31')),
  )
  renderApp('/tasks/11')
  await userEvent.setup().click(await screen.findByRole('button', { name: /Model call 31/ }))
  expect(await screen.findByText('The full log of this call is not kept any more.')).toBeInTheDocument()
})
