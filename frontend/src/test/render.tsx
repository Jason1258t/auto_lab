import { QueryClient } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router'

import { AppRoutes, Providers } from '@/app'

/** The whole app at one address, with a fresh cache and no retries. */
export function renderApp(path = '/') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Providers queryClient={queryClient}>
        <AppRoutes />
      </Providers>
    </MemoryRouter>,
  )
}
