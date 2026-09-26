import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { QualityMetrics } from '../../api/types'
import { formatCurrency, formatPercent } from '../../lib/format'
import { CHART_AXIS, CHART_GRID, SERIES, STATUS_CRITICAL } from '../../lib/chartPalette'
import { ChartCard, EmptyChart } from './ChartCard'
import { ChartTooltip } from './ChartTooltip'
import { StatTile } from './StatTile'

const AXIS_PROPS = { stroke: CHART_AXIS, fontSize: 11, tickLine: false, axisLine: false }

// Mirrors backend/app/metrics.py's CLASSIFIER_EVAL_FIELDS (D-52) so the table
// stays column-stable even as the eval set's own dict grows.
const EVAL_COLUMNS: { key: string; label: string; format: (v: string | number | null) => string }[] = [
  { key: 'classifier', label: 'Classifier', format: (v) => String(v ?? '—') },
  { key: 'n', label: 'n', format: (v) => String(v ?? '—') },
  { key: 'keep_gate_precision', label: 'Keep-gate precision', format: fmt2 },
  { key: 'keep_gate_recall', label: 'Keep-gate recall', format: fmt2 },
  { key: 'keep_gate_roc_auc', label: 'Keep-gate AUC', format: fmt2 },
  { key: 'relevance_accuracy', label: 'Relevance acc.', format: fmt2 },
  { key: 'relevance_roc_auc', label: 'Relevance AUC', format: fmt2 },
  { key: 'newsworthy_roc_auc', label: 'Newsworthy AUC', format: fmt2 },
  { key: 'selection_precision', label: 'Selection precision', format: fmt2 },
  { key: 'latency_p50_ms', label: 'p50 latency', format: (v) => (v == null ? '—' : `${Math.round(Number(v))} ms`) },
  { key: 'latency_p95_ms', label: 'p95 latency', format: (v) => (v == null ? '—' : `${Math.round(Number(v))} ms`) },
  { key: 'cost_per_100', label: 'Cost / 100', format: (v) => (v == null ? '—' : formatCurrency(Number(v), 3)) },
]

function fmt2(v: string | number | null): string {
  return v == null ? '—' : Number(v).toFixed(2)
}

function ClassifierEvalTable({ quality, synthetic }: { quality: QualityMetrics; synthetic: boolean }) {
  return (
    <ChartCard
      title="Classifier eval"
      hint={quality.classifier_eval_date ? `Latest labeled-set run: ${quality.classifier_eval_date}` : 'No eval run found'}
      synthetic={synthetic}
      wide
    >
      {quality.classifier_eval.length === 0 ? (
        <EmptyChart label="No eval results found" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="text-slate-500">
                {EVAL_COLUMNS.map((c) => (
                  <th key={c.key} className="whitespace-nowrap pb-1 pr-3 font-medium">
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="[font-variant-numeric:tabular-nums]">
              {quality.classifier_eval.map((row, i) => (
                <tr key={i} className="border-t border-slate-100 text-slate-700">
                  {EVAL_COLUMNS.map((c) => (
                    <td key={c.key} className="whitespace-nowrap py-1 pr-3">
                      {c.format(row[c.key] ?? null)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </ChartCard>
  )
}

function RatingByPromptVersionChart({ quality, synthetic }: { quality: QualityMetrics; synthetic: boolean }) {
  const data = quality.rating_by_prompt_version.map((r) => {
    const b = r.breakdown
    return {
      version: `${r.script_prompt_version ?? 'unrated'} (n=${b.n_total})`,
      pct_liked: b.pct_liked ?? 0,
      pct_disliked: b.pct_disliked ?? 0,
      pct_not_rated: b.pct_not_rated ?? 0,
      n_liked: b.n_liked,
      n_disliked: b.n_disliked,
      n_not_rated: b.n_not_rated,
    }
  })
  const segmentCount: Record<string, 'n_liked' | 'n_disliked' | 'n_not_rated'> = {
    Liked: 'n_liked',
    Disliked: 'n_disliked',
    'Not rated': 'n_not_rated',
  }
  return (
    <ChartCard
      title="Rating by script prompt version"
      hint="Share of listened sessions that were liked / disliked / not rated"
      synthetic={synthetic}
    >
      {data.length === 0 ? (
        <EmptyChart />
      ) : (
        <ResponsiveContainer width="100%" height={Math.max(160, data.length * 40)}>
          <BarChart data={data} layout="vertical" margin={{ left: 8 }}>
            <CartesianGrid horizontal={false} stroke={CHART_GRID} />
            <XAxis type="number" domain={[0, 1]} tickFormatter={(v) => formatPercent(Number(v))} {...AXIS_PROPS} />
            <YAxis type="category" dataKey="version" width={150} {...AXIS_PROPS} />
            <Tooltip
              content={
                <ChartTooltip
                  formatValue={(v, entry) => {
                    const key = entry?.name ? segmentCount[entry.name] : undefined
                    const n = key ? (entry?.payload?.[key] as number | undefined) : undefined
                    return n == null ? formatPercent(Number(v)) : `${formatPercent(Number(v))} (n=${n})`
                  }}
                />
              }
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="pct_liked" name="Liked" stackId="rating" fill={SERIES.aqua} maxBarSize={22} />
            <Bar dataKey="pct_disliked" name="Disliked" stackId="rating" fill={STATUS_CRITICAL} maxBarSize={22} />
            <Bar
              dataKey="pct_not_rated"
              name="Not rated"
              stackId="rating"
              fill={SERIES.gray}
              radius={[0, 4, 4, 0]}
              maxBarSize={22}
            />
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  )
}

export function QualitySection({ quality, synthetic }: { quality: QualityMetrics; synthetic: boolean }) {
  return (
    <section>
      <h2 className="mb-3 text-base font-semibold text-slate-900">Quality</h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <ClassifierEvalTable quality={quality} synthetic={synthetic} />
        <RatingByPromptVersionChart quality={quality} synthetic={synthetic} />
        <div className="grid grid-cols-2 gap-4 self-start">
          <StatTile
            label="Grounding flags (initial)"
            value={quality.grounding_flags_avg_initial == null ? '—' : quality.grounding_flags_avg_initial.toFixed(2)}
            note="Avg. unsupported claims per episode, before the grounding check"
          />
          <StatTile
            label="Grounding flags (final)"
            value={quality.grounding_flags_avg_final == null ? '—' : quality.grounding_flags_avg_final.toFixed(2)}
            note="After the grounding check's rewrite"
          />
        </div>
      </div>
    </section>
  )
}
