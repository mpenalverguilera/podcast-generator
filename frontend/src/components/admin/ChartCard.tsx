import type { ReactNode } from 'react'

export function ChartCard({
  title,
  hint,
  synthetic,
  wide,
  children,
}: {
  title: string
  hint?: string
  // Shown when the "include synthetic data" toggle is on -- ARCHITECTURE.md
  // §11 / docs/phases/07-dashboard.md: "a note under each chart when the
  // toggle is on".
  synthetic?: boolean
  wide?: boolean
  children: ReactNode
}) {
  return (
    <div
      className={`rounded-xl border border-slate-200 bg-white p-4 shadow-sm ${wide ? 'sm:col-span-2' : ''}`}
    >
      <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
      {hint && <p className="mt-0.5 text-xs text-slate-400">{hint}</p>}
      <div className="mt-3">{children}</div>
      {synthetic && <p className="mt-2 text-[11px] text-slate-400">Includes seeded synthetic data.</p>}
    </div>
  )
}

export function EmptyChart({ label = 'No data in this range' }: { label?: string }) {
  return (
    <div className="flex h-48 items-center justify-center rounded-md bg-slate-50 text-xs text-slate-400">
      {label}
    </div>
  )
}
