// Shared Recharts tooltip content: value leads (bold, high-contrast), series
// name follows (dataviz skill, interaction.md "values lead, labels follow"),
// keyed by a short line stroke rather than a filled swatch.
type TooltipEntry = { name?: string; value?: string | number; color?: string; payload?: Record<string, unknown> }

export function ChartTooltip({
  active,
  label,
  payload,
  formatValue = (v) => String(v),
}: {
  active?: boolean
  label?: string | number
  payload?: TooltipEntry[]
  formatValue?: (value: string | number, entry?: TooltipEntry) => string
}) {
  if (!active || !payload || payload.length === 0) return null
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-md">
      {label !== undefined && <p className="mb-1 font-medium text-slate-500">{String(label)}</p>}
      <ul className="space-y-1">
        {payload.map((entry, i) => (
          <li key={`${entry.name}-${i}`} className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-3 rounded-full" style={{ backgroundColor: entry.color }} />
            <span className="font-semibold text-slate-900">
              {entry.value !== undefined ? formatValue(entry.value, entry) : '—'}
            </span>
            <span className="text-slate-400">{entry.name}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
