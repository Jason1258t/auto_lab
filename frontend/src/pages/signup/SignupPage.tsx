import { useTranslation } from 'react-i18next'
import { Navigate } from 'react-router'

import { useSession } from '@/entities/session'
import { SignupForm } from '@/features/auth'
import { AuthLayout } from '@/widgets/auth-layout'

export function SignupPage() {
  const { t } = useTranslation()
  const { status } = useSession()
  if (status === 'signed_in') return <Navigate to="/" replace />
  return (
    <AuthLayout title={t('auth.signupTitle')}>
      <SignupForm />
    </AuthLayout>
  )
}
