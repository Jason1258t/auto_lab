import '@testing-library/jest-dom/vitest'
import '@/shared/i18n'

import { cleanup } from '@testing-library/react'

import { setAccessToken } from '@/shared/api'

import { server } from './server'

// Every request needs a fake answer: an unknown one fails the test.
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  cleanup()
  server.resetHandlers()
  setAccessToken(null)
  document.documentElement.classList.remove('dark')
  localStorage.clear()
})
afterAll(() => server.close())
