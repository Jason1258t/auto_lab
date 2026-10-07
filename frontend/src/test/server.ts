// A fake backend for tests (MSW, at the network level). Tests add their
// own answers with server.use(...). Default: nobody is logged in.
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'

export const API = '*/api/v1'

export function apiError(status: number, code: string, message: string) {
  return HttpResponse.json({ error: { code, message } }, { status })
}

export const ME = {
  id: 1,
  email: 'ann@example.com',
  username: 'ann',
  display_name: 'Ann',
  email_verified: false,
  created_at: '2026-10-07T10:00:00Z',
  is_admin: false,
}

export const TOKENS = { access_token: 'token-1', token_type: 'bearer', expires_in: 900 }

/** Answers for a returning user: the refresh cookie works. */
export const signedIn = [
  http.post(`${API}/auth/refresh`, () => HttpResponse.json(TOKENS)),
  http.get(`${API}/me`, () => HttpResponse.json(ME)),
]

export const server = setupServer(
  http.post(`${API}/auth/refresh`, () => apiError(401, 'invalid_refresh_token', 'Please log in again')),
)
