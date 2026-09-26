// Route, layout and empty chart cards only -- data and Recharts wiring land
// in phase 07 (docs/phases/06-frontend.md §6, docs/ARCHITECTURE.md §11).
const CARDS = [
  { title: 'DAU / WAU', hint: 'Daily & weekly active users' },
  { title: 'Episodes per day', hint: 'Generation volume over time' },
  { title: 'Listen-through rate', hint: 'Completed vs. started plays' },
  { title: 'Cost per episode', hint: 'By provider — Exa / OpenAI / ElevenLabs' },
  { title: 'Generation time by stage', hint: 'p50 / p95 latency' },
  { title: 'Failure rate by stage', hint: 'Pipeline reliability' },
  { title: 'Classifier comparison', hint: 'Luna vs. Sol agreement, accuracy, cost' },
  { title: 'Rating ratio', hint: '👍 vs 👎 across episodes' },
]

export function AdminPage() {
  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-900">Admin dashboard</h1>
        <label className="flex items-center gap-2 text-sm text-slate-500">
          <input type="checkbox" defaultChecked disabled className="rounded" />
          Include synthetic data
        </label>
      </div>
      <p className="mb-4 text-sm text-slate-500">Charts land in phase 07 — this is the layout shell.</p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {CARDS.map((card) => (
          <div key={card.title} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-900">{card.title}</h2>
            <p className="mt-1 text-xs text-slate-400">{card.hint}</p>
            <div className="mt-4 flex h-24 items-center justify-center rounded-md bg-slate-50 text-xs text-slate-400">
              No data yet
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
