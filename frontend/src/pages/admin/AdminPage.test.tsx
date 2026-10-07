// The admin page and removing a publication, with a fake backend.
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import type { AdminModel } from '@/entities/admin'
import { API, apiError, ME, server, TOKENS } from '@/test/server'
import { renderApp } from '@/test/render'

const asAdmin = [
  http.post(`${API}/auth/refresh`, () => HttpResponse.json(TOKENS)),
  http.get(`${API}/me`, () => HttpResponse.json({ ...ME, is_admin: true })),
]
const PROVIDER = { id: 1, name: 'ollama', adapter: 'ollama', base_url: null }
const MODEL: AdminModel = {
  id: 1, provider_id: 1, name: 'qwen2.5:3b', context_length: 32768, vram_mb: 2500, ram_mb: null,
  cost_per_1m_input: null, cost_per_1m_output: null, description: null, available: false, created_at: '2026-10-07T10:00:00Z',
}

test('an admin adds a model and makes it available', async () => {
  let models = [MODEL]
  const sent: unknown[] = []
  server.use(
    ...asAdmin,
    http.get(`${API}/admin/models`, () => HttpResponse.json(models)),
    http.get(`${API}/admin/model-providers`, () => HttpResponse.json([PROVIDER])),
    http.post(`${API}/admin/models`, async ({ request }) => {
      sent.push(await request.json())
      models = [...models, { ...MODEL, id: 2, name: 'llama3.2:3b', available: true }]
      return HttpResponse.json(models[1], { status: 201 })
    }),
    http.patch(`${API}/admin/models/1`, async ({ request }) => {
      sent.push(await request.json())
      models = [{ ...MODEL, available: true }, ...models.slice(1)]
      return HttpResponse.json(models[0])
    }),
  )
  renderApp('/admin')
  const user = userEvent.setup()
  expect(await screen.findByText('qwen2.5:3b')).toBeInTheDocument()
  expect(screen.getByText(/ollama · 32768 tokens context · 2500 MB VRAM/)).toBeInTheDocument()

  await user.click(screen.getByRole('checkbox', { name: 'Available' }))
  await user.click(screen.getByRole('button', { name: 'Add model' }))
  const dialog = await screen.findByRole('dialog')
  await user.type(within(dialog).getByLabelText('Model name'), 'llama3.2:3b')
  await user.click(within(dialog).getByRole('button', { name: 'Add model' }))
  expect(await screen.findByText('llama3.2:3b')).toBeInTheDocument()
  expect(sent).toEqual([
    { available: true },
    { provider_id: 1, name: 'llama3.2:3b', context_length: 4096, vram_mb: null, description: null },
  ])
})

test('an admin gives admin rights by user id and sees errors', async () => {
  server.use(
    ...asAdmin,
    http.get(`${API}/admin/models`, () => HttpResponse.json([])),
    http.get(`${API}/admin/model-providers`, () => HttpResponse.json([])),
    http.post(`${API}/admin/admins/2`, () => new HttpResponse(null, { status: 204 })),
    http.delete(`${API}/admin/admins/1`, () => apiError(409, 'cannot_revoke_self', 'No')),
  )
  renderApp('/admin?tab=admins')
  const user = userEvent.setup()
  const id = await screen.findByLabelText('User id')
  await user.type(id, '2')
  await user.click(screen.getByRole('button', { name: 'Make admin' }))
  expect(await screen.findByText('User 2 is now an admin.')).toBeInTheDocument()
  await user.clear(id)
  await user.type(id, '1')
  await user.click(screen.getByRole('button', { name: 'Remove admin' }))
  expect(await screen.findByText('You cannot remove your own admin rights.')).toBeInTheDocument()
})

test('other users do not get the admin page or the link', async () => {
  server.use(
    http.post(`${API}/auth/refresh`, () => HttpResponse.json(TOKENS)),
    http.get(`${API}/me`, () => HttpResponse.json(ME)),
  )
  renderApp('/admin')
  expect(await screen.findByText('This page is for admins only.')).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Admin' })).not.toBeInTheDocument()
})

test('an admin removes a publication from the feed', async () => {
  let removed = false
  server.use(
    ...asAdmin,
    http.get(`${API}/publications/3`, () =>
      HttpResponse.json({
        id: 3, title: 'Spam', description: null, published_at: '2026-10-07T12:00:00Z',
        publisher: { id: 4, name: 'X', description: null, created_at: '2026-10-07T10:00:00Z' }, text: 'Buy now.', sources: [],
      }),
    ),
    http.delete(`${API}/admin/publications/3`, () => {
      removed = true
      return new HttpResponse(null, { status: 204 })
    }),
    http.get(`${API}/publications`, () => HttpResponse.json([])),
  )
  renderApp('/publications/3')
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Remove from the feed' }))
  await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Remove from the feed' }))
  expect(await screen.findByText('Nothing is published yet.')).toBeInTheDocument()
  expect(removed).toBe(true)
})
