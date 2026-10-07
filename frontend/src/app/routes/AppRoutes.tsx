import { Route, Routes } from 'react-router'

import { LoginPage } from '@/pages/login'
import { NotFoundPage } from '@/pages/not-found'
import { SignupPage } from '@/pages/signup'
import { TaskPage } from '@/pages/task'
import { WorkPage } from '@/pages/work'
import { WorkspacePage } from '@/pages/workspace'
import { WorkspacesPage } from '@/pages/workspaces'

import { AppLayout, RequireAuth, WaitForSession } from '../layouts/AppLayout'

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
        <Route path="/tasks/:taskId" element={<TaskPage />} />
      </Route>
      {/* Also without login: public workspaces and their accepted works. */}
      <Route
        element={
          <WaitForSession>
            <AppLayout />
          </WaitForSession>
        }
      >
        <Route path="/workspaces/:workspaceId" element={<WorkspacePage />} />
        <Route path="/works/:taskId" element={<WorkPage />} />
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
