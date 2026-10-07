import { useTranslation } from 'react-i18next'
import { Navigate } from 'react-router'

import { useSession } from '@/entities/session'
import { SignupForm, useReturnTo } from '@/features/auth'
import { AuthLayout } from '@/widgets/auth-layout'

export function SignupPage() {
  const { t } = useTranslation()
  const { status } = useSession()
  const returnTo = useReturnTo()
  if (status === 'signed_in') return <Navigate to={returnTo} replace />
  return (
    <AuthLayout title={t('auth.signupTitle')}>
      <SignupForm />
    </AuthLayout>
  )
}
