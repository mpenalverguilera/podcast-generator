import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, getToken, setToken, setUnauthorizedHandler } from '../api/client'
import type { MeResponse } from '../api/types'

interface AuthContextValue {
  token: string | null
  user: MeResponse | null
  isLoading: boolean
  login: (email: string, password: string) => Promise<MeResponse>
  signup: (email: string, password: string) => Promise<MeResponse>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(getToken())
  const queryClient = useQueryClient()

  const meQuery = useQuery({
    queryKey: ['me'],
    queryFn: api.me,
    enabled: token !== null,
    retry: false,
  })

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setTokenState(null)
      queryClient.clear()
    })
  }, [queryClient])

  const signIn = useCallback(
    (access_token: string) => {
      setToken(access_token)
      setTokenState(access_token)
      return queryClient.fetchQuery({ queryKey: ['me'], queryFn: api.me })
    },
    [queryClient],
  )

  const login = useCallback(
    async (email: string, password: string) => signIn((await api.login(email, password)).access_token),
    [signIn],
  )

  // The signup endpoint returns a token, so a new account is signed in at once.
  const signup = useCallback(
    async (email: string, password: string) => signIn((await api.signup(email, password)).access_token),
    [signIn],
  )

  const logout = useCallback(() => {
    setToken(null)
    setTokenState(null)
    queryClient.clear()
  }, [queryClient])

  const value: AuthContextValue = {
    token,
    user: meQuery.data ?? null,
    isLoading: token !== null && meQuery.isLoading,
    login,
    signup,
    logout,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
