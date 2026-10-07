import { useState, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router'

import { errorText } from '@/shared/api'

/** Busy state and error text; after success, back to where the user came
 *  from (RequireAuth remembers it). */
export function useAuthForm(action: () => Promise<void>) {
  const navigate = useNavigate()
  const location = useLocation()
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const from = (location.state as { from?: string } | null)?.from ?? '/'

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await action()
      navigate(from, { replace: true })
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }
  return { error, busy, onSubmit: (event: FormEvent) => void onSubmit(event) }
}
