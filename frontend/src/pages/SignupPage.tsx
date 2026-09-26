import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../api/client'

// Same loose check as the login page and the API (SignupRequest).
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
// Matches SignupRequest: bcrypt only reads the first 72 bytes.
const MIN_PASSWORD = 8
const MAX_PASSWORD = 72

type Field = 'email' | 'password' | 'confirm'

const inputClass = (invalid: boolean) =>
  `w-full rounded-md border px-3 py-2 text-sm placeholder:text-slate-400 focus:outline-none ${
    invalid ? 'border-red-500 focus:border-red-500' : 'border-slate-300 focus:border-accent'
  }`

export function SignupPage() {
  const { token, signup } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPasswords, setShowPasswords] = useState(false)
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({})
  const [emailTaken, setEmailTaken] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  if (token) return <Navigate to="/" replace />

  function validate(): Partial<Record<Field, string>> {
    const found: Partial<Record<Field, string>> = {}
    if (!EMAIL_RE.test(email.trim())) found.email = 'Enter a valid email address, e.g. you@example.com.'
    if (password.length < MIN_PASSWORD) found.password = `Use at least ${MIN_PASSWORD} characters.`
    else if (password.length > MAX_PASSWORD) found.password = `Use at most ${MAX_PASSWORD} characters.`
    if (confirm !== password) found.confirm = 'Passwords do not match.'
    return found
  }

  function clearError(field: Field) {
    setErrors((prev) => ({ ...prev, [field]: undefined }))
    if (field === 'email') setEmailTaken(false)
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setEmailTaken(false)
    const found = validate()
    setErrors(found)
    if (Object.keys(found).length > 0) return

    setSubmitting(true)
    try {
      await signup(email.trim(), password)
      // A new account never has a profile yet, so start at interests.
      navigate('/settings', { replace: true })
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) setEmailTaken(true)
      else setError('Sign up failed. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const passwordType = showPasswords ? 'text' : 'password'

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <form
        onSubmit={onSubmit}
        noValidate
        className="w-full max-w-sm space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Create your account</h1>
          <p className="mt-1 text-sm text-slate-500">Personal Podcast Generator</p>
        </div>

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
              clearError('email')
            }}
            aria-invalid={Boolean(errors.email) || emailTaken}
            aria-describedby={errors.email || emailTaken ? 'email-error' : undefined}
            className={inputClass(Boolean(errors.email) || emailTaken)}
          />
          {errors.email && (
            <p id="email-error" className="mt-1 text-xs text-red-600">
              {errors.email}
            </p>
          )}
          {emailTaken && (
            <p id="email-error" className="mt-1 text-xs text-red-600">
              An account with this email already exists.{' '}
              <Link to="/login" className="font-medium underline">
                Sign in instead
              </Link>
            </p>
          )}
        </div>

        <div>
          <div className="mb-1 flex items-center justify-between">
            <label htmlFor="password" className="block text-sm font-medium text-slate-700">
              Password
            </label>
            <button
              type="button"
              onClick={() => setShowPasswords((v) => !v)}
              aria-pressed={showPasswords}
              aria-controls="password confirm"
              className="text-xs font-medium text-accent hover:text-accent-dark"
            >
              {showPasswords ? 'Hide passwords' : 'Show passwords'}
            </button>
          </div>
          <input
            id="password"
            type={passwordType}
            autoComplete="new-password"
            placeholder={`At least ${MIN_PASSWORD} characters`}
            value={password}
            onChange={(e) => {
              setPassword(e.target.value)
              clearError('password')
            }}
            aria-invalid={Boolean(errors.password)}
            aria-describedby={errors.password ? 'password-error' : undefined}
            className={inputClass(Boolean(errors.password))}
          />
          {errors.password && (
            <p id="password-error" className="mt-1 text-xs text-red-600">
              {errors.password}
            </p>
          )}
        </div>

        <div>
          <label htmlFor="confirm" className="mb-1 block text-sm font-medium text-slate-700">
            Repeat password
          </label>
          <input
            id="confirm"
            type={passwordType}
            autoComplete="new-password"
            placeholder="••••••••"
            value={confirm}
            onChange={(e) => {
              setConfirm(e.target.value)
              clearError('confirm')
            }}
            aria-invalid={Boolean(errors.confirm)}
            aria-describedby={errors.confirm ? 'confirm-error' : undefined}
            className={inputClass(Boolean(errors.confirm))}
          />
          {errors.confirm && (
            <p id="confirm-error" className="mt-1 text-xs text-red-600">
              {errors.confirm}
            </p>
          )}
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-accent px-3 py-2 text-sm font-medium text-white hover:bg-accent-dark disabled:cursor-not-allowed disabled:select-none disabled:opacity-60"
        >
          {submitting ? 'Creating account…' : 'Create account'}
        </button>
        <p className="text-center text-sm text-slate-600">
          Already have an account?{' '}
          <Link to="/login" className="font-medium text-accent hover:text-accent-dark">
            Sign in
          </Link>
        </p>
      </form>
    </div>
  )
}
