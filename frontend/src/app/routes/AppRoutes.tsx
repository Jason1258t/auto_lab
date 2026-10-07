import { Route, Routes } from 'react-router'

import { LoginPage } from '@/pages/login'
import { NotFoundPage } from '@/pages/not-found'
import { SignupPage } from '@/pages/signup'
import { WorkspacesPage } from '@/pages/workspaces'

import { AppLayout, RequireAuth } from '../layouts/AppLayout'

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<WorkspacesPage />} />
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
