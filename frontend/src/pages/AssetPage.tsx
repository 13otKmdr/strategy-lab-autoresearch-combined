import { useState, useMemo, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import type { CycleSummary, Filters, RankedStrategy, SortField } from '../types'
import { INSTRUMENT_NAMES, REGIME_COLORS, REGIME_LABELS } from '../types'
import StrategyChartCarousel from '../components/strategies/StrategyChartCarousel'
import StrategyTable from '../components/strategies/StrategyTable'
import FilterBar from '../components/filters/FilterBar'
import Pagination from '../components/shared/Pagination'
import MetricCard from '../components/shared/MetricCard'
import Badge from '../components/shared/Badge'

const PAGE_SIZE = 10

const DEFAULT_FILTERS: Filters = {
  search: '',
  marketType: '',
  complianceOnly: false,
  minProfitFactor: 0,
  minTotalProfit: 0,
  strategyType: '',
  sortBy: 'composite_score',
  sortDir: 'desc',
  riskView: '025',
}

export default function AssetPage({ cycle }: { cycle: CycleSummary | null }) {
  const { instrument } = useParams<{ instrument: string }>()
  const navigate = useNavigate()
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS)
  const [page, setPage] = useState(1)

  const asset = cycle?.assets?.[instrument || '']

  const updateFilters = useCallback((partial: Partial<Filters>) => {
    setFilters(prev => ({ ...prev, ...partial }))
    setPage(1)
  }, [])

  const filtered = useMemo(() => {
    if (!asset?.ranked_strategies) return []
    let list = [...asset.ranked_strategies]

    if (filters.search) {
      const q = filters.search.toLowerCase()
      list = list.filter(s =>
        s.strategy_name.toLowerCase().includes(q) ||
        s.strategy_type.toLowerCase().includes(q)
      )
    }
    if (filters.strategyType) {
      list = list.filter(s => s.strategy_type === filters.strategyType)
    }
    if (filters.complianceOnly) {
      list = list.filter(s => s.overall_compliance === 'compliant')
    }
    list.sort((a, b) => {
      const aVal = (a as any)[filters.sortBy] ?? 0
      const bVal = (b as any)[filters.sortBy] ?? 0
      return filters.sortDir === 'desc' ? bVal - aVal : aVal - bVal
    })
    return list
  }, [asset, filters])

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const pageStrategies = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  if (!asset || !instrument) {
    return (
      <div className="text-center py-24 text-text-muted">
        {cycle ? `No data for ${instrument}. Run a cycle first.` : 'No cycle data. Run a cycle from the Overview tab.'}
      </div>
    )
  }

  const regimeColor = REGIME_COLORS[asset.regime] || 'text-text-muted'
  const regimeLabel = REGIME_LABELS[asset.regime] || asset.regime
  const scoutData = asset.scout_data

  return (
    <div className="space-y-6">
      {/* Asset Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-2xl font-bold">{instrument}</h2>
            <span className="text-lg text-text-secondary">{INSTRUMENT_NAMES[instrument]}</span>
            <Badge variant={asset.regime === 'trending_up' ? 'green' : asset.regime === 'trending_down' ? 'red' : asset.regime === 'volatile' ? 'purple' : 'amber'}>
              {regimeLabel}
            </Badge>
            <Badge variant={asset.direction_bias === 'bullish' ? 'green' : asset.direction_bias === 'bearish' ? 'red' : 'muted'}>
              {asset.direction_bias}
            </Badge>
          </div>
          {scoutData && (
            <p className="text-sm text-text-muted mt-1">
              Price: ${scoutData.current_price?.toFixed(2)} ({scoutData.price_change_pct >= 0 ? '+' : ''}{scoutData.price_change_pct?.toFixed(2)}%)
              {scoutData.buy_and_hold_2y ? ` · 2Y B&H: ${scoutData.buy_and_hold_2y >= 0 ? '+' : ''}${scoutData.buy_and_hold_2y?.toFixed(1)}%` : ''}
              {scoutData.sentiment_label ? ` · Sentiment: ${scoutData.sentiment_label}` : ''}
            </p>
          )}
        </div>
        <div className="text-right">
          <p className="text-xs text-text-muted">Confidence</p>
          <p className="text-lg font-semibold">{(asset.regime_strength * 100).toFixed(0)}%</p>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
        <MetricCard label="Strategies" value={asset.total_strategies} />
        <MetricCard label="Tests" value={asset.total_tests} />
        <MetricCard label="Compliant" value={asset.compliant_count} color="text-accent-green" />
        <MetricCard label="Non-Compliant" value={asset.non_compliant_count} color="text-accent-red" />
        <MetricCard label="Best PF" value={asset.best_profit_factor.toFixed(2)} color="text-accent-blue" />
        <MetricCard label="Avg Score" value={asset.avg_composite_score.toFixed(1)} />
      </div>

      {/* Chart Carousel */}
      <StrategyChartCarousel strategies={asset.ranked_strategies} />

      {/* Filters + Table */}
      <FilterBar filters={filters} onChange={updateFilters} />

      <div className="bg-surface-800/50 border border-border rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <p className="text-sm text-text-secondary">
            Showing {pageStrategies.length} of {filtered.length} strategies
            {filters.riskView === '025' ? ' @ 0.25% risk' : ' @ 0.5% risk'}
          </p>
        </div>
        <StrategyTable strategies={pageStrategies} filters={filters} />
        <div className="px-4 pb-3">
          <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
        </div>
      </div>
    </div>
  )
}
