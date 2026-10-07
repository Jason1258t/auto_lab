import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'

import { SessionProvider } from '@/entities/session'
import { ThemeProvider } from '@/shared/lib/theme'

/** Everything a page needs around it. Tests use the same providers with a
 *  memory router (src/test/render.tsx). */
export function Providers({ children, queryClient }: { children: ReactNode; queryClient?: QueryClient }) {
  const [client] = useState(
    () => queryClient ?? new QueryClient({ defaultOptions: { queries: { staleTime: 10_000 } } }),
  )
  return (
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <SessionProvider>{children}</SessionProvider>
      </ThemeProvider>
    </QueryClientProvider>
  )
}
