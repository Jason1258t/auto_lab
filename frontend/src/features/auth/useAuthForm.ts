import { useState, type FormEvent } from 'react'
import { useLocation } from 'react-router'

import { errorText } from '@/shared/api'

/** Where to go after login or signup: the page RequireAuth sent the user
 *  away from, or the start page. */
export function useReturnTo(): string {
  const location = useLocation()
  return (location.state as { from?: string } | null)?.from ?? '/'
}

/** Busy state and error text. After success the session becomes
 *  "signed in" and the page redirects (to useReturnTo()). */
export function useAuthForm(action: () => Promise<void>) {
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await action()
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }
  return { error, busy, onSubmit: (event: FormEvent) => void onSubmit(event) }
}
