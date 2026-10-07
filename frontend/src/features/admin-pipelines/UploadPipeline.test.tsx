// The Pipelines tab of the admin page: list, YAML, check and upload.
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import type { AdminPipeline } from '@/entities/admin'
import { API, apiError, ME, server, TOKENS } from '@/test/server'
import { renderApp } from '@/test/render'

import { nextVersion } from './UploadPipelineButton'

const RESEARCH: AdminPipeline = {
  id: 1,
  name: 'research',
  description: 'Any topic',
  versions: [
    { id: 2, version_name: '1.1.0', uploaded: false, tasks: 3, created_at: '2026-10-07T10:00:00Z' },
    { id: 1, version_name: '1.0.0', uploaded: false, tasks: 9, created_at: '2026-10-01T10:00:00Z' },
  ],
}

function asAdmin(pipelines: () => AdminPipeline[]) {
  return [
    http.post(`${API}/auth/refresh`, () => HttpResponse.json(TOKENS)),
    http.get(`${API}/me`, () => HttpResponse.json({ ...ME, is_admin: true })),
    http.get(`${API}/admin/pipelines`, () => HttpResponse.json(pipelines())),
    http.get(`${API}/admin/pipeline-versions/2/file`, () => HttpResponse.text('pipeline: research\nversion: 1.1.0\n')),
  ]
}

test('next version', () => {
  expect(nextVersion('1.1.0')).toBe('1.2.0')
  expect(nextVersion(undefined)).toBe('1.0.0')
})

test('the list shows versions and their YAML', async () => {
  server.use(...asAdmin(() => [RESEARCH]))
  renderApp('/admin?tab=pipelines')
  const user = userEvent.setup()
  expect(await screen.findByText('research')).toBeInTheDocument()
  expect(screen.getByText(/3 tasks/)).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: /1\.1\.0/ }))
  expect(await screen.findByText(/version: 1\.1\.0/)).toBeInTheDocument()
})

test('a new version: fields filled in, check first, then upload', async () => {
  let list = [RESEARCH]
  const sent: Record<string, string>[] = []
  server.use(
    ...asAdmin(() => list),
    http.post(`${API}/admin/pipelines/upload`, async ({ request }) => {
      const form = await request.formData()
      const fields = { name: String(form.get('name')), version: String(form.get('version')), dry_run: String(form.get('dry_run')) }
      sent.push(fields)
      const saved = fields.dry_run === 'false'
      if (saved) list = [{ ...RESEARCH, versions: [{ ...RESEARCH.versions[0], id: 3, version_name: '1.2.0', uploaded: true, tasks: 0 }, ...RESEARCH.versions] }]
      return HttpResponse.json(
        {
          pipeline_id: 1,
          name: 'research',
          version_id: saved ? 3 : null,
          version_name: '1.2.0',
          created_pipeline: false,
          saved,
          notes: ["'version' in the file was 1.1.0; set to 1.2.0"],
        },
        { status: 201 },
      )
    }),
  )
  renderApp('/admin?tab=pipelines')
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Upload pipeline' }))
  const dialog = await screen.findByRole('dialog')
  expect(within(dialog).getByLabelText('Name')).toHaveValue('research')
  expect(within(dialog).getByLabelText('Version')).toHaveValue('1.2.0')
  expect(within(dialog).getByText('Newest now: 1.1.0. The new one must be higher.')).toBeInTheDocument()

  await user.upload(within(dialog).getByLabelText('YAML file'), new File(['pipeline: research'], 'r.yaml'))
  await user.click(within(dialog).getByRole('button', { name: 'Check' }))
  expect(await within(dialog).findByText('The file is valid. Nothing is saved yet.')).toBeInTheDocument()
  expect(within(dialog).getByText("'version' in the file was 1.1.0; set to 1.2.0")).toBeInTheDocument()

  await user.click(within(dialog).getByRole('button', { name: 'Upload' }))
  expect(await within(dialog).findByText('Saved: research 1.2.0. New tasks use it now.')).toBeInTheDocument()
  expect(sent.map((f) => f.dry_run)).toEqual(['true', 'false'])
  await user.click(within(dialog).getByRole('button', { name: 'Done' }))
  expect(await screen.findByText('uploaded')).toBeInTheDocument()
})

test('a new pipeline, and validation problems one per line', async () => {
  server.use(
    ...asAdmin(() => [RESEARCH]),
    http.post(`${API}/admin/pipelines/upload`, () =>
      apiError(422, 'invalid_pipeline', "my_steps 1.0.0: step 'x': unknown kind 'run_shell'; step 'y': the id is used twice"),
    ),
  )
  renderApp('/admin?tab=pipelines')
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Upload pipeline' }))
  const dialog = await screen.findByRole('dialog')
  await user.selectOptions(within(dialog).getByLabelText('What is it?'), 'A new pipeline')
  expect(within(dialog).getByLabelText('Name')).toHaveValue('')
  expect(within(dialog).getByLabelText('Version')).toHaveValue('1.0.0')
  await user.type(within(dialog).getByLabelText('Name'), 'my_steps')
  await user.upload(within(dialog).getByLabelText('YAML file'), new File(['x'], 'x.yaml'))
  await user.click(within(dialog).getByRole('button', { name: 'Check' }))
  const problem = await within(dialog).findByText(/unknown kind 'run_shell'/)
  expect(problem.textContent).toContain("'run_shell'\nstep 'y'")
})
