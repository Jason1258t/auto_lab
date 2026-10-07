// The files tab, with a fake backend.
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import type { WorkspaceFile } from '@/entities/file'
import type { Workspace } from '@/entities/workspace'
import { API, apiError, server, signedIn } from '@/test/server'
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
const NOTES: WorkspaceFile = {
  id: 3,
  original_name: 'notes.txt',
  original_path: null,
  file_name: 'a1b2.txt',
  size_bytes: 1234,
  sha256: 'x',
  content_type: 'text/plain',
  uploaded_by: 1,
  created_at: '2026-10-07T10:00:00Z',
}

function workspace(w: Workspace, files: () => WorkspaceFile[]) {
  return [
    ...signedIn,
    http.get(`${API}/workspaces/7`, () => HttpResponse.json(w)),
    http.get(`${API}/workspaces/7/files`, () => HttpResponse.json(files())),
  ]
}

test('the owner uploads files; a failed one is named', async () => {
  let files: WorkspaceFile[] = []
  const names: string[] = []
  server.use(
    ...workspace(OWNED, () => files),
    http.post(`${API}/workspaces/7/files`, async ({ request }) => {
      const file = (await request.formData()).get('file') as File
      names.push(file.name)
      if (file.name === 'big.pdf') return apiError(413, 'file_too_large', 'Too large')
      files = [...files, { ...NOTES, id: files.length + 1, original_name: file.name }]
      return HttpResponse.json(files.at(-1), { status: 201 })
    }),
  )
  renderApp('/workspaces/7?tab=files')
  const user = userEvent.setup()
  expect(await screen.findByText('No files yet.')).toBeInTheDocument()

  await user.upload(screen.getByTestId('file-input'), [
    new File(['hello'], 'notes.txt', { type: 'text/plain' }),
    new File(['x'], 'big.pdf'),
  ])
  expect(await screen.findByText('“big.pdf” was not uploaded: The file is too large.')).toBeInTheDocument()
  expect(await screen.findByText('notes.txt')).toBeInTheDocument()
  expect(names).toEqual(['notes.txt', 'big.pdf'])
})

test('a member downloads but cannot upload or remove', async () => {
  const member: Workspace = { ...OWNED, owner_id: 9, is_owner: false, my_roles: ['member'] }
  let downloaded = false
  server.use(
    ...workspace(member, () => [NOTES]),
    http.get(`${API}/workspaces/7/files/3/download`, () => {
      downloaded = true
      return new HttpResponse('hello', { headers: { 'content-type': 'text/plain' } })
    }),
  )
  URL.createObjectURL = vi.fn(() => 'blob:x')
  URL.revokeObjectURL = vi.fn()
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  renderApp('/workspaces/7?tab=files')
  const user = userEvent.setup()
  expect(await screen.findByText('notes.txt')).toBeInTheDocument()
  expect(screen.getByText('1.2 kB', { exact: false })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Upload files' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Remove notes.txt' })).not.toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'Download notes.txt' }))
  await waitFor(() => expect(click).toHaveBeenCalled())
  expect(downloaded).toBe(true)
  click.mockRestore()
})

test('the owner removes a file after confirming', async () => {
  let files = [NOTES]
  server.use(
    ...workspace(OWNED, () => files),
    http.delete(`${API}/workspaces/7/files/3`, () => {
      files = []
      return new HttpResponse(null, { status: 204 })
    }),
  )
  renderApp('/workspaces/7?tab=files')
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Remove notes.txt' }))
  await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Remove' }))
  expect(await screen.findByText('No files yet.')).toBeInTheDocument()
})
