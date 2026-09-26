import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../api/client'

// Deliberately loose: just "something@something.tld". The server's lookup is
// the real check; this only catches typos before a round trip.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export function LoginPage() {
  const { token, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [emailError, setEmailError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  if (token) {
    const from = (location.state as { from?: string } | null)?.from ?? '/'
    return <Navigate to={from} replace />
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!EMAIL_RE.test(email.trim())) {
      setEmailError('Enter a valid email address, e.g. you@example.com.')
      return
    }
    if (!password) {
      setError('Enter your password.')
      return
    }
    setSubmitting(true)
    try {
      const me = await login(email.trim(), password)
      navigate(me.has_profile ? '/' : '/settings', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? 'Invalid email or password.' : 'Login failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <form onSubmit={onSubmit} noValidate className="w-full max-w-sm space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-xl font-semibold text-slate-900">Personal Podcast Generator</h1>
        <div>
          <label htmlFor="email" className="mb-1 block text-sm font-medium text-slate-700">
            Email
          </label>
          <input
            id="email"
            type="email"
            autoFocus
            autoComplete="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value)
              setEmailError(null)
            }}
            aria-invalid={emailError !== null}
            aria-describedby={emailError ? 'email-error' : undefined}
            className={`w-full rounded-md border px-3 py-2 text-sm placeholder:text-slate-400 focus:outline-none ${
              emailError ? 'border-red-500 focus:border-red-500' : 'border-slate-300 focus:border-accent'
            }`}
          />
          {emailError && (
            <p id="email-error" className="mt-1 text-xs text-red-600">
              {emailError}
            </p>
          )}
        </div>
        <div>
          <label htmlFor="password" className="mb-1 block text-sm font-medium text-slate-700">
            Password
          </label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm placeholder:text-slate-400 focus:border-accent focus:outline-none"
          />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-accent px-3 py-2 text-sm font-medium text-white hover:bg-accent-dark disabled:opacity-60"
        >
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
        <p className="text-center text-sm text-slate-600">
          No account yet?{' '}
          <Link to="/signup" className="font-medium text-accent hover:text-accent-dark">
            Create one
          </Link>
        </p>
      </form>
    </div>
  )
}
