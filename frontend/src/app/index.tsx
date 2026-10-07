import './styles/index.css'
import '@/shared/i18n'

import { BrowserRouter } from 'react-router'

import { Providers } from './providers/Providers'
import { AppRoutes } from './routes/AppRoutes'

export { AppRoutes, Providers }

export function App() {
  return (
    <BrowserRouter>
      <Providers>
        <AppRoutes />
      </Providers>
    </BrowserRouter>
  )
}
