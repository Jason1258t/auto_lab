// The work page and the Works lists, with a fake backend.
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import type { Work } from '@/entities/work'
import type { Workspace } from '@/entities/workspace'
import { API, apiError, server, signedIn } from '@/test/server'
import { renderApp } from '@/test/render'

const WORK: Work = {
  task_id: 11,
  workspace_id: 7,
  title: 'Why is the sky blue?',
  task_status: 'done',
  summary: 'Rayleigh scattering.',
  text: [
    '# Why is the sky blue?',
    '',
    '## Light',
    '',
    'Short waves scatter more [1]. The sky is always blue. *(⚠ no source)*',
    '',
    '<script>alert(1)</script>',
    '',
    'A [bad](javascript:alert(1)) link.',
    '',
    '## Sources',
    '',
    '**[1]** Blue light scatters more — "Blue light is scattered more." ([Site A](http://site-a.test/sky))',
  ].join('\n'),
  updated_at: '2026-10-07T10:00:00Z',
  sources: [
    {
      id: 1,
      title: 'Site A',
      kind: 'web',
      location: 'http://site-a.test/sky',
      accessed_at: '2026-10-07T10:00:00Z',
      quotes: [{ id: 1, claim: 'Blue light scatters more', quote: 'Blue light is scattered more.', placement: null }],
    },
  ],
}
const PUBLIC: Workspace = {
  id: 7,
  name: 'Sky research',
  description: null,
  visibility: 'public',
  owner_id: 9,
  owner_username: 'zoe',
  owner_display_name: 'Zoe',
  archived_at: null,
  created_at: '2026-10-07T10:00:00Z',
  is_owner: false,
  my_roles: [],
}

test('a work shows its text, the no-source marks and the evidence', async () => {
  server.use(...signedIn, http.get(`${API}/tasks/11/work`, () => HttpResponse.json(WORK)))
  const { container } = renderApp('/works/11')
  expect(await screen.findByRole('heading', { name: 'Light' })).toBeInTheDocument()
  expect(screen.getByText('1 sentence has no source. Check it before you accept the work.')).toBeInTheDocument()
  expect(screen.getByText('(⚠ no source)')).toHaveClass('text-destructive')
  // The quote, linked to its source.
  expect(screen.getByText('Blue light is scattered more.')).toBeInTheDocument()
  expect(screen.getAllByRole('link', { name: 'Site A' })[0]).toHaveAttribute('rel', 'noopener noreferrer nofollow')
  // Model or web text never becomes HTML or a script link.
  expect(container.querySelector('script')).toBeNull()
  expect(screen.getByText('bad').closest('a')?.getAttribute('href') ?? '').not.toContain('javascript')
  expect(screen.getByRole('link', { name: '← Workspace' })).toHaveAttribute('href', '/workspaces/7')
})

test('anyone can read a public workspace and its accepted works, without login', async () => {
  server.use(
    http.get(`${API}/workspaces/7`, () => HttpResponse.json(PUBLIC)),
    http.get(`${API}/workspaces/7/works`, () =>
      HttpResponse.json([{ task_id: 11, title: 'Why is the sky blue?', task_status: 'done', summary: 'Rayleigh scattering.', updated_at: '2026-10-07T10:00:00Z' }]),
    ),
  )
  renderApp('/workspaces/7')
  expect(await screen.findByRole('link', { name: 'Why is the sky blue?' })).toHaveAttribute('href', '/works/11')
  expect(screen.queryByRole('tab')).not.toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Log in' })).toBeInTheDocument()
})

test('a missing work shows a clear message', async () => {
  server.use(...signedIn, http.get(`${API}/tasks/12/work`, () => apiError(404, 'work_not_found', 'No work')))
  renderApp('/works/12')
  expect(await screen.findByText('This work does not exist, or you have no access to it.')).toBeInTheDocument()
})
