import { STAGE_ORDER } from '../api/types'

const LABELS: Record<string, string> = {
  pending: 'Pending',
  planning: 'Planning',
  fetching: 'Fetching news',
  ranking: 'Ranking stories',
  extracting: 'Reading articles',
  scripting: 'Writing script',
  voicing: 'Recording voices',
  assembling: 'Mixing audio',
  ready: 'Ready',
  failed: 'Failed',
}

export function statusLabel(status: string): string {
  return LABELS[status] ?? status
}

export function StatusBadge({ status }: { status: string }) {
  const color =
    status === 'ready'
      ? 'bg-emerald-100 text-emerald-700'
      : status === 'failed'
        ? 'bg-red-100 text-red-700'
        : 'bg-amber-100 text-amber-700'
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${color}`}>
      {statusLabel(status)}
    </span>
  )
}

// A small stepper across the pipeline's stage order, current stage highlighted.
export function StageStepper({ status }: { status: string }) {
  const currentIndex = STAGE_ORDER.indexOf(status as (typeof STAGE_ORDER)[number])
  return (
    <ol className="flex flex-wrap items-center gap-1 text-xs text-slate-500">
      {STAGE_ORDER.map((stage, i) => {
        const done = currentIndex >= 0 && i < currentIndex
        const active = i === currentIndex
        return (
          <li key={stage} className="flex items-center gap-1">
            <span
              className={`h-2 w-2 rounded-full ${
                active ? 'bg-accent' : done ? 'bg-emerald-400' : 'bg-slate-200'
              }`}
            />
            <span className={active ? 'font-medium text-accent' : undefined}>{statusLabel(stage)}</span>
            {i < STAGE_ORDER.length - 1 && <span className="mx-1 text-slate-300">›</span>}
          </li>
        )
      })}
    </ol>
  )
}
