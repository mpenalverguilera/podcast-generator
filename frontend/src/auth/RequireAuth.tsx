import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from './AuthContext'
import { Spinner } from '../components/Spinner'

export function RequireAuth({ children }: { children: ReactNode }) {
  const { token, isLoading } = useAuth()

  if (!token) return <Navigate to="/login" replace />
  if (isLoading) return <Spinner />
  return <>{children}</>
}

export function RequireAdmin({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  if (!user?.is_admin) return <Navigate to="/" replace />
  return <>{children}</>
}
