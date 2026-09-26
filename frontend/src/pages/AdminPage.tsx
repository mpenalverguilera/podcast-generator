import { useMemo, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { OperationsSection } from '../components/admin/OperationsSection'
import { ProductSection } from '../components/admin/ProductSection'
import { QualitySection } from '../components/admin/QualitySection'
import { StatTile } from '../components/admin/StatTile'
import { Spinner } from '../components/Spinner'
import { RANGE_PRESETS, rangeForPreset, type RangePreset } from '../lib/dates'
import { formatCurrency, formatPercent } from '../lib/format'

export function AdminPage() {
  const [days, setDays] = useState<RangePreset>(30)
  const [includeSynthetic, setIncludeSynthetic] = useState(true)
  const { from, to } = useMemo(() => rangeForPreset(days), [days])

  const query = useQuery({
    queryKey: ['admin-metrics', from, to, includeSynthetic],
    queryFn: () => api.adminMetrics({ from, to, includeSynthetic }),
    placeholderData: keepPreviousData,
  })

  const data = query.data

  const episodeCount = data
    ? data.product.episodes_per_day.reduce((sum, d) => sum + d.manual + d.scheduled, 0)
    : null
  const latestWau = data && data.product.wau.length > 0 ? data.product.wau[data.product.wau.length - 1].count : null
  const costPerEpisode =
    data && episodeCount ? data.operations.total_spend_usd / episodeCount : null

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold text-slate-900">Admin dashboard</h1>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex rounded-md border border-slate-200 bg-white p-0.5 text-sm">
            {RANGE_PRESETS.map((preset) => (
              <button
                key={preset}
                onClick={() => setDays(preset)}
                className={`rounded px-2.5 py-1 font-medium ${
                  days === preset ? 'bg-accent text-white' : 'text-slate-600 hover:bg-slate-100'
                }`}
              >
                {preset}d
              </button>
            ))}
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={includeSynthetic}
              onChange={(e) => setIncludeSynthetic(e.target.checked)}
              className="rounded"
            />
            Include synthetic data
          </label>
          {includeSynthetic && (
            <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-700">
              Includes mock data
            </span>
          )}
        </div>
      </div>

      {query.isLoading ? (
        <Spinner />
      ) : query.isError || !data ? (
        <p className="text-sm text-red-600">Could not load metrics.</p>
      ) : (
        <div className={`space-y-8 transition-opacity ${query.isFetching ? 'opacity-60' : ''}`}>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatTile label="WAU" value={latestWau == null ? '—' : String(latestWau)} />
            <StatTile label="Episodes" value={episodeCount == null ? '—' : String(episodeCount)} />
            <StatTile label="Listen-through rate" value={formatPercent(data.product.listen_through_rate)} />
            <StatTile
              label="Cost / episode"
              value={formatCurrency(costPerEpisode)}
              note={data.operations.total_spend_includes_estimate ? 'Includes an ElevenLabs estimate' : undefined}
            />
          </div>

          <ProductSection product={data.product} synthetic={includeSynthetic} />
          <OperationsSection operations={data.operations} synthetic={includeSynthetic} />
          <QualitySection quality={data.quality} synthetic={includeSynthetic} />
        </div>
      )}
    </div>
  )
}
