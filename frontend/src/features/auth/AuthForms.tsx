import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { useSession } from '@/entities/session'
import { Button, FormError, FormField } from '@/shared/ui'

import { useAuthForm } from './useAuthForm'

function SwitchLink({ question, to, label }: { question: string; to: string; label: string }) {
  return (
    <p className="text-center text-sm text-muted-foreground">
      {question}{' '}
      <Link to={to} className="text-primary underline-offset-4 hover:underline">
        {label}
      </Link>
    </p>
  )
}

export function LoginForm() {
  const { t } = useTranslation()
  const { login } = useSession()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const form = useAuthForm(() => login(email, password))
  return (
    <form onSubmit={form.onSubmit} className="grid gap-4">
      <FormField id="email" label={t('auth.email')} type="email" value={email} onChange={setEmail} autoComplete="email" />
      <FormField id="password" label={t('auth.password')} type="password" value={password} onChange={setPassword} autoComplete="current-password" />
      <FormError error={form.error} />
      <Button type="submit" disabled={form.busy}>
        {t('auth.login')}
      </Button>
      <SwitchLink question={t('auth.noAccount')} to="/signup" label={t('auth.signup')} />
    </form>
  )
}

export function SignupForm() {
  const { t } = useTranslation()
  const { signup } = useSession()
  const [values, setValues] = useState({ email: '', username: '', display_name: '', password: '' })
  const set = (key: keyof typeof values) => (value: string) => setValues((v) => ({ ...v, [key]: value }))
  const form = useAuthForm(() => signup(values))
  return (
    <form onSubmit={form.onSubmit} className="grid gap-4">
      <FormField id="email" label={t('auth.email')} type="email" value={values.email} onChange={set('email')} autoComplete="email" />
      <FormField id="username" label={t('auth.username')} value={values.username} onChange={set('username')} hint={t('auth.usernameHint')} autoComplete="username" />
      <FormField id="display_name" label={t('auth.displayName')} value={values.display_name} onChange={set('display_name')} autoComplete="name" />
      <FormField id="password" label={t('auth.password')} type="password" value={values.password} onChange={set('password')} hint={t('auth.passwordHint')} autoComplete="new-password" />
      <FormError error={form.error} />
      <Button type="submit" disabled={form.busy}>
        {t('auth.signup')}
      </Button>
      <SwitchLink question={t('auth.haveAccount')} to="/login" label={t('auth.login')} />
    </form>
  )
}
