import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { ProductMetrics } from '../../api/types'
import { formatShortDay } from '../../lib/dates'
import { formatPercent } from '../../lib/format'
import { CHART_AXIS, CHART_GRID, SERIES } from '../../lib/chartPalette'
import { ChartCard, EmptyChart } from './ChartCard'
import { ChartTooltip } from './ChartTooltip'
import { StatTile } from './StatTile'

const AXIS_PROPS = { stroke: CHART_AXIS, fontSize: 11, tickLine: false, axisLine: false }

function DauWauChart({ product, synthetic }: { product: ProductMetrics; synthetic: boolean }) {
  const byDay = new Map<string, { day: string; dau: number; wau: number }>()
  for (const p of product.dau) byDay.set(p.day, { day: p.day, dau: p.count, wau: 0 })
  for (const p of product.wau) {
    const row = byDay.get(p.day) ?? { day: p.day, dau: 0, wau: 0 }
    row.wau = p.count
    byDay.set(p.day, row)
  }
  const data = [...byDay.values()].sort((a, b) => a.day.localeCompare(b.day))

  return (
    <ChartCard title="DAU / WAU" hint="Daily and weekly active users" synthetic={synthetic} wide>
      {data.length === 0 ? (
        <EmptyChart />
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data} margin={{ left: -20 }}>
            <CartesianGrid vertical={false} stroke={CHART_GRID} />
            <XAxis dataKey="day" tickFormatter={formatShortDay} {...AXIS_PROPS} />
            <YAxis allowDecimals={false} {...AXIS_PROPS} />
            <Tooltip
              content={<ChartTooltip formatValue={(v) => String(v)} />}
              labelFormatter={(label) => formatShortDay(String(label))}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line type="monotone" dataKey="dau" name="DAU" stroke={SERIES.blue} strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="wau" name="WAU" stroke={SERIES.orange} strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  )
}

function NewUsersChart({ product, synthetic }: { product: ProductMetrics; synthetic: boolean }) {
  return (
    <ChartCard title="New users / day" hint="Signups over time" synthetic={synthetic}>
      {product.new_users_per_day.length === 0 ? (
        <EmptyChart />
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={product.new_users_per_day} margin={{ left: -20 }}>
            <CartesianGrid vertical={false} stroke={CHART_GRID} />
            <XAxis dataKey="day" tickFormatter={formatShortDay} {...AXIS_PROPS} />
            <YAxis allowDecimals={false} {...AXIS_PROPS} />
            <Tooltip content={<ChartTooltip />} labelFormatter={(label) => formatShortDay(String(label))} />
            <Bar dataKey="count" name="New users" fill={SERIES.blue} radius={[4, 4, 0, 0]} maxBarSize={24} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  )
}

function EpisodesPerDayChart({ product, synthetic }: { product: ProductMetrics; synthetic: boolean }) {
  return (
    <ChartCard title="Episodes / day" hint="Manual vs. scheduled generation" synthetic={synthetic}>
      {product.episodes_per_day.length === 0 ? (
        <EmptyChart />
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={product.episodes_per_day} margin={{ left: -20 }}>
            <CartesianGrid vertical={false} stroke={CHART_GRID} />
            <XAxis dataKey="day" tickFormatter={formatShortDay} {...AXIS_PROPS} />
            <YAxis allowDecimals={false} {...AXIS_PROPS} />
            <Tooltip content={<ChartTooltip />} labelFormatter={(label) => formatShortDay(String(label))} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="manual" name="Manual" stackId="episodes" fill={SERIES.blue} maxBarSize={24} />
            <Bar
              dataKey="scheduled"
              name="Scheduled"
              stackId="episodes"
              fill={SERIES.orange}
              radius={[4, 4, 0, 0]}
              maxBarSize={24}
            />
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  )
}

function TopTopicsChart({ product, synthetic }: { product: ProductMetrics; synthetic: boolean }) {
  const data = [...product.top_topics].sort((a, b) => b.count - a.count).slice(0, 8)
  return (
    <ChartCard title="Top topics" hint="Most-selected article topics" synthetic={synthetic}>
      {data.length === 0 ? (
        <EmptyChart />
      ) : (
        <ResponsiveContainer width="100%" height={Math.max(160, data.length * 32)}>
          <BarChart data={data} layout="vertical" margin={{ left: 8 }}>
            <CartesianGrid horizontal={false} stroke={CHART_GRID} />
            <XAxis type="number" allowDecimals={false} {...AXIS_PROPS} />
            <YAxis type="category" dataKey="topic" width={120} {...AXIS_PROPS} />
            <Tooltip content={<ChartTooltip />} />
            <Bar dataKey="count" name="Episodes" fill={SERIES.blue} radius={[0, 4, 4, 0]} maxBarSize={18} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  )
}

function RetentionTable({ product, synthetic }: { product: ProductMetrics; synthetic: boolean }) {
  return (
    <ChartCard
      title="7-day retention"
      hint="Signed up in week N, played again in week N+1"
      synthetic={synthetic}
    >
      {product.retention.length === 0 ? (
        <EmptyChart label="No cohorts have matured in this range" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="text-slate-500">
                <th className="pb-1 pr-3 font-medium">Cohort week</th>
                <th className="pb-1 pr-3 font-medium">Size</th>
                <th className="pb-1 pr-3 font-medium">Retained</th>
                <th className="pb-1 font-medium">Rate</th>
              </tr>
            </thead>
            <tbody className="[font-variant-numeric:tabular-nums]">
              {product.retention.map((r) => (
                <tr key={r.cohort_week} className="border-t border-slate-100 text-slate-700">
                  <td className="py-1 pr-3">{formatShortDay(r.cohort_week)}</td>
                  <td className="py-1 pr-3">{r.cohort_size}</td>
                  <td className="py-1 pr-3">{r.retained}</td>
                  <td className="py-1 font-semibold text-slate-900">{formatPercent(r.retention_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </ChartCard>
  )
}

function RatingStatRow({ product }: { product: ProductMetrics }) {
  const b = product.rating_breakdown
  const note = (n: number) => `${n} of ${b.n_total} listened`
  return (
    <div className="grid grid-cols-3 gap-4">
      <StatTile label="👍 Liked" value={formatPercent(b.pct_liked)} note={note(b.n_liked)} />
      <StatTile label="👎 Disliked" value={formatPercent(b.pct_disliked)} note={note(b.n_disliked)} />
      <StatTile label="Not rated" value={formatPercent(b.pct_not_rated)} note={note(b.n_not_rated)} />
    </div>
  )
}

export function ProductSection({ product, synthetic }: { product: ProductMetrics; synthetic: boolean }) {
  return (
    <section>
      <h2 className="mb-3 text-base font-semibold text-slate-900">Product</h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <DauWauChart product={product} synthetic={synthetic} />
        <NewUsersChart product={product} synthetic={synthetic} />
        <EpisodesPerDayChart product={product} synthetic={synthetic} />
        <TopTopicsChart product={product} synthetic={synthetic} />
        <RetentionTable product={product} synthetic={synthetic} />
        <div className="flex flex-col gap-4 self-start">
          <RatingStatRow product={product} />
          <div className="grid grid-cols-3 gap-4">
            <StatTile label="Focus-request usage" value={formatPercent(product.focus_request_usage_rate)} />
            <StatTile label="Avg. % listened" value={formatPercent(product.avg_percent_listened)} />
            <StatTile label="Listen-through rate" value={formatPercent(product.listen_through_rate)} />
          </div>
        </div>
      </div>
    </section>
  )
}
