/// <reference types="node" />
import '@testing-library/jest-dom/vitest'
import '@/shared/i18n'

import { cleanup } from '@testing-library/react'

import { setAccessToken } from '@/shared/api'

import { server } from './server'

// jsdom's FormData and File cannot be sent by Node's fetch (the upload
// never starts). Use Node's own classes, which work like a browser's.
const nodeForm = await new Response(new URLSearchParams()).formData()
globalThis.FormData = nodeForm.constructor as typeof FormData
globalThis.File = (await import('node:buffer')).File as unknown as typeof File

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
