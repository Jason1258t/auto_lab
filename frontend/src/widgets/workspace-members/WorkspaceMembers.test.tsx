// The members block on the workspace page, with a fake backend.
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import type { Member } from '@/entities/member'
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
const BOB: Member = { user_id: 2, username: 'bob', display_name: 'Bob', roles: ['member'] }
const CAT: Member = { user_id: 3, username: 'cat', display_name: 'Cat', roles: ['editor', 'member'] }

/** `members` is a function, so a test can change the list later. */
function workspace(w: Workspace, members: () => Member[]) {
  return [
    ...signedIn,
    http.get(`${API}/workspaces/7`, () => HttpResponse.json(w)),
    http.get(`${API}/workspaces/7/members`, () => HttpResponse.json(members())),
  ]
}

test('the owner adds a person and sees an unknown name as an error', async () => {
  let members = [BOB]
  server.use(
    ...workspace(OWNED, () => members),
    http.post(`${API}/workspaces/7/members`, async ({ request }) => {
      const { username_or_email } = (await request.json()) as { username_or_email: string }
      if (username_or_email !== 'cat') return apiError(404, 'user_not_found', 'No user')
      members = [BOB, { ...CAT, roles: ['member'] }]
      return HttpResponse.json(members[1], { status: 201 })
    }),
  )
  renderApp('/workspaces/7')
  const user = userEvent.setup()
  expect(await screen.findByText('Bob')).toBeInTheDocument()
  expect(screen.getByText('@ann')).toBeInTheDocument() // the owner is listed first

  await user.type(screen.getByLabelText('Add a person'), 'nobody')
  await user.click(screen.getByRole('button', { name: 'Add' }))
  expect(await screen.findByText('There is no user with this username or email.')).toBeInTheDocument()

  await user.clear(screen.getByLabelText('Add a person'))
  await user.type(screen.getByLabelText('Add a person'), ' cat ')
  await user.click(screen.getByRole('button', { name: 'Add' }))
  expect(await screen.findByText('Cat')).toBeInTheDocument()
  expect(screen.getByLabelText('Add a person')).toHaveValue('')
})

test('the owner grants and removes roles with the checkboxes', async () => {
  const calls: string[] = []
  const path = `${API}/workspaces/7/members/2/roles/:role`
  server.use(
    ...workspace(OWNED, () => [BOB]),
    http.put(path, ({ params }) => {
      calls.push(`PUT ${String(params.role)}`)
      return HttpResponse.json({ ...BOB, roles: ['member', String(params.role)] })
    }),
    http.delete(path, ({ params }) => {
      calls.push(`DELETE ${String(params.role)}`)
      return HttpResponse.json(BOB)
    }),
  )
  renderApp('/workspaces/7')
  const user = userEvent.setup()
  const editor = await screen.findByRole('checkbox', { name: 'Editor' })
  expect(editor).not.toBeChecked()
  await user.click(editor)
  expect(await screen.findByRole('checkbox', { name: 'Editor', checked: true })).toBeInTheDocument()
  await user.click(screen.getByRole('checkbox', { name: 'Editor' }))
  expect(await screen.findByRole('checkbox', { name: 'Editor', checked: false })).toBeInTheDocument()
  expect(calls).toEqual(['PUT editor', 'DELETE editor'])
})

test('an editor manages only reviewers and cannot add or remove people', async () => {
  const asEditor: Workspace = { ...OWNED, owner_id: 9, is_owner: false, my_roles: ['editor', 'member'] }
  server.use(...workspace(asEditor, () => [BOB, CAT]))
  renderApp('/workspaces/7')
  expect(await screen.findByText('Bob')).toBeInTheDocument()
  expect(screen.getAllByRole('checkbox', { name: 'Reviewer' })).toHaveLength(2)
  expect(screen.queryByRole('checkbox', { name: 'Editor' })).not.toBeInTheDocument()
  expect(screen.getByText('Editor')).toBeInTheDocument() // Cat's role, as a badge
  expect(screen.queryByLabelText('Add a person')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Remove Bob' })).not.toBeInTheDocument()
})

test('the owner removes a person after confirming', async () => {
  let members = [BOB, CAT]
  server.use(
    ...workspace(OWNED, () => members),
    http.delete(`${API}/workspaces/7/members/2`, () => {
      members = [CAT]
      return new HttpResponse(null, { status: 204 })
    }),
  )
  renderApp('/workspaces/7')
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Remove Bob' }))
  const dialog = screen.getByRole('alertdialog')
  await user.click(within(dialog).getByRole('button', { name: 'Remove' }))
  await waitFor(() => expect(screen.queryByText('Bob')).not.toBeInTheDocument())
  expect(screen.getByText('Cat')).toBeInTheDocument()
})

test('a visitor of a public workspace does not see the members', async () => {
  const visitor: Workspace = { ...OWNED, visibility: 'public', owner_id: 9, is_owner: false }
  server.use(...signedIn, http.get(`${API}/workspaces/7`, () => HttpResponse.json(visitor)))
  renderApp('/workspaces/7')
  expect(await screen.findByRole('heading', { name: 'Sky research' })).toBeInTheDocument()
  expect(screen.queryByText('Members')).not.toBeInTheDocument()
})
