// The workspace list and one workspace page, through the whole app with a
// fake backend.
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import type { Workspace } from '@/entities/workspace'
import { API, apiError, server, signedIn } from '@/test/server'
import { renderApp } from '@/test/render'

const MINE: Workspace = {
  id: 7,
  name: 'Sky research',
  description: 'Why is the sky blue?',
  visibility: 'private',
  owner_id: 1,
  archived_at: null,
  created_at: '2026-10-07T10:00:00Z',
  is_owner: true,
  my_roles: [],
}
const FREE: Workspace = {
  ...MINE,
  id: 9,
  name: 'Old notes',
  visibility: 'public',
  owner_id: null,
  archived_at: '2026-10-01T10:00:00Z',
  is_owner: false,
}

test('the tabs load my, public and free workspaces', async () => {
  const scopes: (string | null)[] = []
  server.use(
    ...signedIn,
    http.get(`${API}/workspaces`, ({ request }) => {
      const scope = new URL(request.url).searchParams.get('scope')
      scopes.push(scope)
      return HttpResponse.json(scope === 'free' ? [FREE] : [MINE])
    }),
  )
  renderApp('/')
  expect(await screen.findByText('Sky research')).toBeInTheDocument()
  await userEvent.setup().click(screen.getByRole('tab', { name: 'Free to take' }))
  expect(await screen.findByText('Old notes')).toBeInTheDocument()
  expect(scopes).toEqual(['mine', 'free'])
})

test('a new workspace opens its page', async () => {
  let sent: unknown = null
  server.use(
    ...signedIn,
    http.get(`${API}/workspaces`, () => HttpResponse.json([])),
    http.post(`${API}/workspaces`, async ({ request }) => {
      sent = await request.json()
      return HttpResponse.json({ ...MINE, id: 8, name: 'Bees', description: null }, { status: 201 })
    }),
    http.get(`${API}/workspaces/8`, () => HttpResponse.json({ ...MINE, id: 8, name: 'Bees', description: null })),
  )
  renderApp('/')
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'New workspace' }))
  await user.type(screen.getByLabelText('Name'), '  Bees ')
  await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'New workspace' }))

  expect(await screen.findByRole('heading', { name: 'Bees' })).toBeInTheDocument()
  expect(sent).toEqual({ name: 'Bees', description: '' })
})

test('the owner edits the name and description', async () => {
  let current = MINE
  server.use(
    ...signedIn,
    http.get(`${API}/workspaces/7`, () => HttpResponse.json(current)),
    http.patch(`${API}/workspaces/7`, async ({ request }) => {
      current = { ...current, ...((await request.json()) as object), description: null }
      return HttpResponse.json(current)
    }),
  )
  renderApp('/workspaces/7')
  const user = userEvent.setup()
  expect(await screen.findByText('Why is the sky blue?')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Edit' }))
  const name = screen.getByLabelText('Name')
  expect(name).toHaveValue('Sky research')
  await user.clear(name)
  await user.type(name, 'Blue sky')
  await user.clear(screen.getByLabelText('Description'))
  await user.click(screen.getByRole('button', { name: 'Save' }))

  expect(await screen.findByRole('heading', { name: 'Blue sky' })).toBeInTheDocument()
  expect(screen.queryByText('Why is the sky blue?')).not.toBeInTheDocument()
})

test('archive asks first and shows the error from the backend', async () => {
  server.use(
    ...signedIn,
    http.get(`${API}/workspaces/7`, () => HttpResponse.json(MINE)),
    http.post(`${API}/workspaces/7/archive`, () =>
      apiError(409, 'workspace_archived', 'The workspace is archived (read-only)'),
    ),
  )
  renderApp('/workspaces/7')
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Archive' }))
  const dialog = screen.getByRole('alertdialog')
  expect(within(dialog).getByText('Archive “Sky research”?')).toBeInTheDocument()
  await user.click(within(dialog).getByRole('button', { name: 'Archive' }))
  expect(await within(dialog).findByText('This workspace is archived. It is read-only.')).toBeInTheDocument()
})

test('a free workspace can be taken', async () => {
  let current = FREE
  server.use(
    ...signedIn,
    http.get(`${API}/workspaces/9`, () => HttpResponse.json(current)),
    http.post(`${API}/workspaces/9/take`, () => {
      current = { ...FREE, owner_id: 1, archived_at: null, is_owner: true }
      return HttpResponse.json(current)
    }),
  )
  renderApp('/workspaces/9')
  const user = userEvent.setup()
  expect(await screen.findByText('This workspace is archived. It is read-only.')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Take' }))
  await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Take' }))

  expect(await screen.findByRole('button', { name: 'Edit' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Take' })).not.toBeInTheDocument()
})

test('an unknown workspace shows a clear message', async () => {
  server.use(
    ...signedIn,
    http.get(`${API}/workspaces/404`, () => apiError(404, 'workspace_not_found', 'Workspace 404 not found')),
  )
  renderApp('/workspaces/404')
  expect(
    await screen.findByText('This workspace does not exist, or you have no access to it.'),
  ).toBeInTheDocument()
})
