import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { OperationsMetrics } from '../../api/types'
import { statusLabel } from '../StatusBadge'
import { formatShortDay } from '../../lib/dates'
import { formatCompact, formatCurrency, formatPercent } from '../../lib/format'
import { CHART_AXIS, CHART_GRID, SERIES, STATUS_CRITICAL, orderProviders, providerColor, providerLabel } from '../../lib/chartPalette'
import { ChartCard, EmptyChart } from './ChartCard'
import { ChartTooltip } from './ChartTooltip'
import { StatTile } from './StatTile'

const AXIS_PROPS = { stroke: CHART_AXIS, fontSize: 11, tickLine: false, axisLine: false }

// pipeline_steps.stage values: statusLabel covers every episode status
// (which is most of them, by design) except "grounding" -- the script
// stage's own extra row (D-30), never an episode status.
function stageLabel(stage: string): string {
  return stage === 'grounding' ? 'Grounding check' : statusLabel(stage)
}

function StageLatencyChart({ operations, synthetic }: { operations: OperationsMetrics; synthetic: boolean }) {
  return (
    <ChartCard
      title="Generation time (ms) by stage"
      hint="p50 / p95 latency, successful steps only"
      synthetic={synthetic}
      wide
    >
      {operations.stage_latency.length === 0 ? (
        <EmptyChart />
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={operations.stage_latency} margin={{ left: -10 }}>
            <CartesianGrid vertical={false} stroke={CHART_GRID} />
            <XAxis dataKey="stage" tickFormatter={stageLabel} interval={0} {...AXIS_PROPS} />
            <YAxis allowDecimals={false} tickFormatter={formatCompact} {...AXIS_PROPS} />
            <Tooltip
              content={<ChartTooltip formatValue={(v) => `${Math.round(Number(v)).toLocaleString()} ms`} />}
              labelFormatter={(label) => stageLabel(String(label))}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="p50_ms" name="p50" fill={SERIES.blue} maxBarSize={32} />
            <Bar dataKey="p95_ms" name="p95" fill={SERIES.orange} radius={[4, 4, 0, 0]} maxBarSize={32} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  )
}

function StageFailureChart({ operations, synthetic }: { operations: OperationsMetrics; synthetic: boolean }) {
  return (
    <ChartCard title="Failure rate by stage" hint="Share of steps that failed" synthetic={synthetic} wide>
      {operations.stage_failure_rate.length === 0 ? (
        <EmptyChart />
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={operations.stage_failure_rate} margin={{ left: -10 }}>
            <CartesianGrid vertical={false} stroke={CHART_GRID} />
            <XAxis dataKey="stage" tickFormatter={stageLabel} interval={0} {...AXIS_PROPS} />
            {/* With no failures every bar is 0 and Recharts' auto domain draws 0-400%;
                keep at least a 0-5% axis so "no failures" reads as flat bars (D-73). */}
            <YAxis
              domain={[0, (dataMax: number) => Math.max(dataMax, 0.05)]}
              tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
              {...AXIS_PROPS}
            />
            <Tooltip
              content={<ChartTooltip formatValue={(v) => formatPercent(Number(v), 1)} />}
              labelFormatter={(label) => stageLabel(String(label))}
            />
            <Bar dataKey="failure_rate" name="Failure rate" fill={STATUS_CRITICAL} radius={[4, 4, 0, 0]} maxBarSize={32} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  )
}

function CostByProviderChart({ operations, synthetic }: { operations: OperationsMetrics; synthetic: boolean }) {
  const byDay = new Map<string, Record<string, number | string>>()
  const totals = new Map<string, number>()
  let hasEstimate = false
  for (const row of operations.cost_per_day_by_provider) {
    if (row.cost_is_estimate) hasEstimate = true
    totals.set(row.provider, (totals.get(row.provider) ?? 0) + row.cost_usd)
    const day = byDay.get(row.day) ?? { day: row.day }
    day[row.provider] = row.cost_usd
    byDay.set(row.day, day)
  }
  const data = [...byDay.values()].sort((a, b) => String(a.day).localeCompare(String(b.day)))
  // "local"/"fake" (assemble, or fake-adapter runs) always cost $0 -- fold
  // them out rather than seat a zero-height legend entry.
  const order = orderProviders([...totals].filter(([, total]) => total > 0).map(([provider]) => provider))

  return (
    <ChartCard title="Cost per day by provider" hint="Exa / OpenAI / ElevenLabs" synthetic={synthetic} wide>
      {order.length === 0 ? (
        // Also when every row is a $0 provider (local ffmpeg, fake adapters): a
        // grid with no bars looks broken (D-73).
        <EmptyChart label="No provider spend in this range" />
      ) : (
        <>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data} margin={{ left: -10 }}>
              <CartesianGrid vertical={false} stroke={CHART_GRID} />
              <XAxis dataKey="day" tickFormatter={formatShortDay} {...AXIS_PROPS} />
              <YAxis tickFormatter={(v: number) => `$${v}`} {...AXIS_PROPS} />
              <Tooltip
                content={<ChartTooltip formatValue={(v) => formatCurrency(Number(v))} />}
                labelFormatter={(label) => formatShortDay(String(label))}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} formatter={providerLabel} />
              {order.map((provider, i) => (
                <Bar
                  key={provider}
                  dataKey={provider}
                  name={providerLabel(provider)}
                  stackId="cost"
                  fill={providerColor(provider)}
                  radius={i === order.length - 1 ? [4, 4, 0, 0] : undefined}
                  maxBarSize={24}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
          {hasEstimate && (
            <p className="mt-2 text-[11px] text-slate-400">
              ElevenLabs $ figures are an estimate (units_in × a configured $/character rate — the real plan
              price isn't visible with this key, D-12); characters (units_in) are the exact number.
            </p>
          )}
        </>
      )}
    </ChartCard>
  )
}

export function OperationsSection({ operations, synthetic }: { operations: OperationsMetrics; synthetic: boolean }) {
  const episodeCostNote = operations.total_spend_includes_estimate ? 'Includes an ElevenLabs estimate' : undefined
  return (
    <section>
      <h2 className="mb-3 text-base font-semibold text-slate-900">Operations</h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <StageLatencyChart operations={operations} synthetic={synthetic} />
        <StageFailureChart operations={operations} synthetic={synthetic} />
        <CostByProviderChart operations={operations} synthetic={synthetic} />
        <div className="grid grid-cols-2 gap-4 self-start">
          <StatTile
            label="Total spend"
            value={formatCurrency(operations.total_spend_usd)}
            note={episodeCostNote}
          />
          <StatTile
            label="Cost / listened minute"
            value={formatCurrency(operations.cost_per_listened_minute)}
            note={episodeCostNote}
          />
        </div>
      </div>
    </section>
  )
}
