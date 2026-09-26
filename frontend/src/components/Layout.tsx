import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

function navClass({ isActive }: { isActive: boolean }) {
  return `rounded-md px-3 py-2 text-sm font-medium ${
    isActive ? 'bg-accent text-white' : 'text-slate-600 hover:bg-slate-100'
  }`
}

export function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth()

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-4xl flex-wrap items-center gap-2 px-4 py-3">
          <span className="mr-2 text-sm font-semibold text-slate-900">🎙️ Podcast</span>
          <nav className="flex flex-1 gap-1">
            {user?.has_profile ? (
              <NavLink to="/" className={navClass} end>
                Episodes
              </NavLink>
            ) : (
              <span
                title="Add your interests first"
                aria-disabled="true"
                className="cursor-not-allowed rounded-md px-3 py-2 text-sm font-medium text-slate-300"
              >
                Episodes
              </span>
            )}
            <NavLink to="/settings" className={navClass}>
              Interests &amp; settings
            </NavLink>
            {user?.is_admin && (
              <NavLink to="/admin" className={navClass}>
                Dashboard
              </NavLink>
            )}
          </nav>
          <span className="hidden text-sm text-slate-500 sm:inline">{user?.email}</span>
          <button
            onClick={logout}
            className="rounded-md px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100"
          >
            Log out
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-4xl px-4 py-6">{children}</main>
    </div>
  )
}
