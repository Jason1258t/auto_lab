// Login, signup and the session, through the whole app with a fake backend.
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { API, apiError, ME, server, signedIn, TOKENS } from '@/test/server'
import { renderApp } from '@/test/render'

const WORKSPACE = {
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

function workspacesAnswer() {
  return http.get(`${API}/workspaces`, () => HttpResponse.json([WORKSPACE]))
}

test('a signed-out user is sent to the login page', async () => {
  renderApp('/')
  expect(await screen.findByRole('heading', { name: 'Log in to AutoLab' })).toBeInTheDocument()
})

test('wrong password shows the error and stays on the page', async () => {
  server.use(
    http.post(`${API}/auth/login`, () => apiError(401, 'invalid_credentials', 'Wrong email or password')),
  )
  renderApp('/login')
  const user = userEvent.setup()
  await user.type(await screen.findByLabelText('Email'), 'ann@example.com')
  await user.type(screen.getByLabelText('Password'), 'wrong password')
  await user.click(screen.getByRole('button', { name: 'Log in' }))

  expect(await screen.findByText('Wrong email or password.')).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Log in to AutoLab' })).toBeInTheDocument()
})

test('login opens the workspaces with the access token', async () => {
  let authHeader: string | null = null
  server.use(
    http.post(`${API}/auth/login`, () => HttpResponse.json(TOKENS)),
    http.get(`${API}/me`, ({ request }) => {
      authHeader = request.headers.get('authorization')
      return HttpResponse.json(ME)
    }),
    workspacesAnswer(),
  )
  renderApp('/login')
  const user = userEvent.setup()
  await user.type(await screen.findByLabelText('Email'), 'ann@example.com')
  await user.type(screen.getByLabelText('Password'), 'a long enough password')
  await user.click(screen.getByRole('button', { name: 'Log in' }))

  expect(await screen.findByText('Sky research')).toBeInTheDocument()
  expect(screen.getByText('Ann')).toBeInTheDocument()
  expect(authHeader).toBe('Bearer token-1')
})

test('a returning user stays logged in (silent refresh)', async () => {
  server.use(...signedIn, workspacesAnswer())
  renderApp('/')
  expect(await screen.findByText('Sky research')).toBeInTheDocument()
})

test('an expired access token is refreshed once and the request is repeated', async () => {
  let refreshes = 0
  let workspaceCalls = 0
  server.use(
    http.post(`${API}/auth/refresh`, () => {
      refreshes += 1
      return HttpResponse.json({ ...TOKENS, access_token: `token-${refreshes}` })
    }),
    http.get(`${API}/me`, () => HttpResponse.json(ME)),
    http.get(`${API}/workspaces`, ({ request }) => {
      workspaceCalls += 1
      // The first token "expired": only the second one is accepted.
      if (request.headers.get('authorization') !== 'Bearer token-2') {
        return apiError(401, 'not_authenticated', 'Please log in')
      }
      return HttpResponse.json([WORKSPACE])
    }),
  )
  renderApp('/')
  expect(await screen.findByText('Sky research')).toBeInTheDocument()
  expect(refreshes).toBe(2) // start of the app, then once for the 401
  expect(workspaceCalls).toBe(2)
})

test('when the refresh fails too, the user goes back to login', async () => {
  let refreshes = 0
  server.use(
    http.post(`${API}/auth/refresh`, () => {
      refreshes += 1
      return refreshes === 1 ? HttpResponse.json(TOKENS) : apiError(401, 'invalid_refresh_token', 'x')
    }),
    http.get(`${API}/me`, () => HttpResponse.json(ME)),
    http.get(`${API}/workspaces`, () => apiError(401, 'not_authenticated', 'Please log in')),
  )
  renderApp('/')
  expect(await screen.findByRole('heading', { name: 'Log in to AutoLab' })).toBeInTheDocument()
})

test('signup creates the account, logs in and opens the app', async () => {
  let signupBody: unknown = null
  server.use(
    http.post(`${API}/auth/signup`, async ({ request }) => {
      signupBody = await request.json()
      return HttpResponse.json({ ...ME, is_admin: undefined }, { status: 201 })
    }),
    http.post(`${API}/auth/login`, () => HttpResponse.json(TOKENS)),
    http.get(`${API}/me`, () => HttpResponse.json(ME)),
    http.get(`${API}/workspaces`, () => HttpResponse.json([])),
  )
  renderApp('/signup')
  const user = userEvent.setup()
  await user.type(await screen.findByLabelText('Email'), 'ann@example.com')
  await user.type(screen.getByLabelText('Username'), 'ann')
  await user.type(screen.getByLabelText('Name'), 'Ann')
  await user.type(screen.getByLabelText('Password'), 'a long enough password')
  await user.click(screen.getByRole('button', { name: 'Sign up' }))

  expect(await screen.findByText('No workspaces yet.')).toBeInTheDocument()
  expect(signupBody).toEqual({
    email: 'ann@example.com',
    username: 'ann',
    display_name: 'Ann',
    password: 'a long enough password',
  })
})

test('logout ends the session', async () => {
  let loggedOut = false
  server.use(
    ...signedIn,
    workspacesAnswer(),
    http.post(`${API}/auth/logout`, () => {
      loggedOut = true
      return new HttpResponse(null, { status: 204 })
    }),
  )
  renderApp('/')
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Log out' }))
  expect(await screen.findByRole('heading', { name: 'Log in to AutoLab' })).toBeInTheDocument()
  await waitFor(() => expect(loggedOut).toBe(true))
})

test('a validation error names the wrong fields', async () => {
  server.use(
    http.post(`${API}/auth/signup`, () =>
      HttpResponse.json(
        {
          error: {
            code: 'validation_error',
            message: 'Invalid request',
            details: [{ loc: ['body', 'email'], msg: 'bad domain' }],
          },
        },
        { status: 422 },
      ),
    ),
  )
  renderApp('/signup')
  const user = userEvent.setup()
  await user.type(await screen.findByLabelText('Email'), 'dev@example.test')
  await user.type(screen.getByLabelText('Username'), 'dev')
  await user.type(screen.getByLabelText('Name'), 'Dev')
  await user.type(screen.getByLabelText('Password'), 'a long enough password')
  await user.click(screen.getByRole('button', { name: 'Sign up' }))
  expect(
    await screen.findByText('Some fields are not filled in correctly. Check: email.'),
  ).toBeInTheDocument()
})
