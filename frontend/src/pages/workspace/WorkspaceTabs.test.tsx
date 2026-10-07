// The tabs on the workspace page: who sees which tab, tasks and activity.
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import type { ActivityEvent } from '@/entities/activity'
import type { Task } from '@/entities/task'
import type { Workspace } from '@/entities/workspace'
import { API, server, signedIn } from '@/test/server'
import { renderApp } from '@/test/render'

const OWNED: Workspace = {
  id: 7,
  name: 'Sky research',
  description: null,
  visibility: 'private',
  owner_id: 1,
  archived_at: null,
  created_at: '2026-10-07T10:00:00Z',
  is_owner: true,
  my_roles: [],
}
const TASK: Task = {
  id: 11,
  workspace_id: 7,
  title: 'Why is the sky blue?',
  input: 'Explain it',
  status: 'in_review',
  pipeline_name: 'research',
  pipeline_version: '1.0.0',
  pipeline_version_id: 1,
  model_id: 1,
  created_by: 1,
  reviewer_id: null,
  created_at: '2026-10-07T10:00:00Z',
  started_at: null,
  finished_at: null,
}
const EVENT: ActivityEvent = {
  id: 1,
  occurred_at: '2026-10-07T10:00:00Z',
  actor_id: 1,
  actor_name: 'Ann',
  action: 'role_added',
  target_type: 'user',
  target_id: 2,
  target_label: 'bob',
  details: { role: 'editor' },
}

function workspace(w: Workspace) {
  return [
    ...signedIn,
    http.get(`${API}/workspaces/7`, () => HttpResponse.json(w)),
    http.get(`${API}/workspaces/7/tasks`, () => HttpResponse.json([TASK])),
    http.get(`${API}/workspaces/7/activity`, () =>
      HttpResponse.json([EVENT, { ...EVENT, id: 2, action: 'something_new', details: null }]),
    ),
  ]
}

test('the tasks tab is first and shows status', async () => {
  server.use(...workspace(OWNED))
  renderApp('/workspaces/7')
  expect(await screen.findByText('Why is the sky blue?')).toBeInTheDocument()
  expect(screen.getByText('In review')).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: 'Tasks', selected: true })).toBeInTheDocument()
})

test('the owner reads the activity log; unknown actions do not break it', async () => {
  server.use(...workspace(OWNED))
  renderApp('/workspaces/7')
  await userEvent.setup().click(await screen.findByRole('tab', { name: 'Activity' }))
  expect(await screen.findByText('Ann gave bob the Editor role')).toBeInTheDocument()
  expect(screen.getByText('something_new')).toBeInTheDocument()
})

test('a plain member has no activity tab', async () => {
  server.use(...workspace({ ...OWNED, owner_id: 9, is_owner: false, my_roles: ['member'] }))
  renderApp('/workspaces/7')
  expect(await screen.findByRole('tab', { name: 'Files' })).toBeInTheDocument()
  expect(screen.queryByRole('tab', { name: 'Activity' })).not.toBeInTheDocument()
})
