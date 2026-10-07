// Typed API client. Types come from the backend's OpenAPI description
// (src/api/schema.d.ts, `npm run api:types`), so a renamed field in the
// backend becomes a type error here.
//
// Tokens (backend_spec.md, section 5):
// - the access token lives only in memory (never in localStorage, where a
//   script injected into the page could read it);
// - the refresh token is an httpOnly cookie the browser sends to
//   /api/v1/auth itself. On a 401 we refresh once and retry the request.
import createClient from 'openapi-fetch'

import type { paths } from './schema'

// Absolute URLs: needed in tests (Node's fetch has no page to be relative to).
const origin = globalThis.location?.origin ?? ''

let accessToken: string | null = null
let refreshing: Promise<boolean> | null = null
const sessionEndListeners = new Set<() => void>()

export function setAccessToken(token: string | null): void {
  accessToken = token
}

export function hasAccessToken(): boolean {
  return accessToken !== null
}

/** Called when the session cannot be refreshed any more (log in again). */
export function onSessionEnd(listener: () => void): () => void {
  sessionEndListeners.add(listener)
  return () => sessionEndListeners.delete(listener)
}

/** Get a new access token with the refresh cookie. Parallel callers share
 *  one request, because each refresh replaces the cookie (rotation). */
export function refreshSession(): Promise<boolean> {
  refreshing ??= fetch(`${origin}/api/v1/auth/refresh`, {
    method: 'POST',
    credentials: 'same-origin',
  })
    .then(async (response) => {
      if (!response.ok) {
        accessToken = null
        return false
      }
      const body = (await response.json()) as { access_token: string }
      accessToken = body.access_token
      return true
    })
    .catch(() => false)
    .finally(() => {
      refreshing = null
    })
  return refreshing
}

async function authFetch(request: Request): Promise<Response> {
  const retry = request.clone()
  if (accessToken) request.headers.set('Authorization', `Bearer ${accessToken}`)
  const response = await fetch(request)
  // The auth routes answer 401 for a wrong password: no refresh there.
  if (response.status !== 401 || new URL(request.url).pathname.startsWith('/api/v1/auth/')) {
    return response
  }
  if (!(await refreshSession())) {
    sessionEndListeners.forEach((listener) => listener())
    return response
  }
  retry.headers.set('Authorization', `Bearer ${accessToken}`)
  return fetch(retry)
}

export const api = createClient<paths>({ baseUrl: origin, fetch: authFetch })
