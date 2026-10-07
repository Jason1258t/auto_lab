// The session: who is logged in. On start the app tries a silent refresh (the httpOnly
// cookie), so a returning user stays logged in after a page reload.
import { useQueryClient } from '@tanstack/react-query'
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import { api, call, onSessionEnd, refreshSession, setAccessToken, type components } from '@/shared/api'

export type Me = components['schemas']['MeOut']
type SignupBody = components['schemas']['SignupIn']

type SessionState = {
  status: 'loading' | 'signed_in' | 'signed_out'
  me: Me | null
  login: (email: string, password: string) => Promise<void>
  signup: (body: SignupBody) => Promise<void>
  logout: () => Promise<void>
}

const SessionContext = createContext<SessionState | null>(null)

async function loadMe(): Promise<Me> {
  return call(api.GET('/api/v1/me'))
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<SessionState['status']>('loading')
  const [me, setMe] = useState<Me | null>(null)

  const signedOut = useCallback(() => {
    setAccessToken(null)
    setMe(null)
    setStatus('signed_out')
    queryClient.clear() // no data of the last user stays in the cache
  }, [queryClient])

  useEffect(() => {
    let active = true
    void (async () => {
      const ok = await refreshSession()
      if (!active) return
      if (!ok) return signedOut()
      try {
        const loaded = await loadMe()
        if (active) {
          setMe(loaded)
          setStatus('signed_in')
        }
      } catch {
        if (active) signedOut()
      }
    })()
    const unsubscribe = onSessionEnd(signedOut)
    return () => {
      active = false
      unsubscribe()
    }
  }, [signedOut])

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await call(api.POST('/api/v1/auth/login', { body: { email, password } }))
    setAccessToken(tokens.access_token)
    setMe(await loadMe())
    setStatus('signed_in')
  }, [])

  const signup = useCallback(
    async (body: SignupBody) => {
      await call(api.POST('/api/v1/auth/signup', { body }))
      await login(body.email, body.password)
    },
    [login],
  )

  const logout = useCallback(async () => {
    try {
      await call(api.POST('/api/v1/auth/logout'))
    } finally {
      signedOut()
    }
  }, [signedOut])

  const value = useMemo(
    () => ({ status, me, login, signup, logout }),
    [status, me, login, signup, logout],
  )
  return <SessionContext value={value}>{children}</SessionContext>
}

export function useSession(): SessionState {
  const state = useContext(SessionContext)
  if (!state) throw new Error('useSession outside SessionProvider')
  return state
}
