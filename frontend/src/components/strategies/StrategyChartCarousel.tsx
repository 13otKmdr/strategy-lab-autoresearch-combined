import { useState, useEffect } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import type { RankedStrategy } from '../../types'
import LightweightChart, { equityCurveToChartData } from '../charts/LightweightChart'
import ChartToggle from '../shared/ChartToggle'
import ComplianceBadge from '../shared/ComplianceBadge'
import { getEquityCurves } from '../../api/client'

export default function StrategyChartCarousel({ strategies }: { strategies: RankedStrategy[] }) {
  const [index, setIndex] = useState(0)
  const [chartMode, setChartMode] = useState<'dollar' | 'percent'>('dollar')
  const [equityData, setEquityData] = useState<{ eq025: number[]; eq050: number[] } | null>(null)
  const [loading, setLoading] = useState(false)

  const top = strategies.slice(0, 10) // carousel through top 10
  const current = top[index]

  useEffect(() => {
    if (!current) return
    setLoading(true)
    getEquityCurves(current.strategy_id)
      .then(data => {
        setEquityData({
          eq025: data?.['0.25']?.equity_curve || [],
          eq050: data?.['0.50']?.equity_curve || [],
        })
      })
      .catch(() => setEquityData(null))
      .finally(() => setLoading(false))
  }, [current?.strategy_id])

  if (!current) {
    return <div className="bg-surface-800 border border-border rounded-lg p-8 text-center text-text-muted">No strategies to display</div>
  }

  const data025 = equityData ? equityCurveToChartData(equityData.eq025, chartMode) : []
  const data050 = equityData ? equityCurveToChartData(equityData.eq050, chartMode) : []

  return (
    <div className="bg-surface-800 border border-border rounded-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-3">
          <span className="text-xs text-text-muted">#{current.rank}</span>
          <span className="font-medium">{current.strategy_name}</span>
          <span className="text-sm text-accent-blue font-mono">{current.composite_score.toFixed(1)}</span>
          <ComplianceBadge status={current.overall_compliance} />
        </div>
        <div className="flex items-center gap-3">
          <ChartToggle mode={chartMode} onChange={setChartMode} />
          <div className="flex items-center gap-1">
            <button
              onClick={() => setIndex(Math.max(0, index - 1))}
              disabled={index === 0}
              className="p-1.5 rounded-md text-text-muted hover:text-text-primary hover:bg-surface-700 disabled:opacity-30 transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="text-xs text-text-muted w-12 text-center">{index + 1} / {top.length}</span>
            <button
              onClick={() => setIndex(Math.min(top.length - 1, index + 1))}
              disabled={index >= top.length - 1}
              className="p-1.5 rounded-md text-text-muted hover:text-text-primary hover:bg-surface-700 disabled:opacity-30 transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Chart */}
      <div className="p-4">
        {loading ? (
          <div className="h-[300px] flex items-center justify-center text-text-muted">Loading chart...</div>
        ) : (
          <LightweightChart
            data025={data025}
            data050={data050}
            mode={chartMode}
            height={300}
            title={chartMode === 'dollar' ? 'Account Balance ($)' : 'Account Growth (%)'}
          />
        )}
      </div>

      {/* Quick stats */}
      <div className="grid grid-cols-4 gap-px bg-border">
        <Stat label="Return (0.25%)" value={`${(current.total_return_pct_025 * 100).toFixed(2)}%`} positive={current.total_return_pct_025 >= 0} />
        <Stat label="Profit Factor" value={current.profit_factor_025 === Infinity ? '∞' : current.profit_factor_025.toFixed(2)} positive={current.profit_factor_025 >= 1.5} />
        <Stat label="Max DD" value={`${(current.max_drawdown_pct_025 * 100).toFixed(2)}%`} positive={current.max_drawdown_pct_025 <= 0.04} />
        <Stat label="Win Rate" value={`${(current.win_rate_025 * 100).toFixed(1)}%`} positive={current.win_rate_025 >= 0.5} />
      </div>
    </div>
  )
}

function Stat({ label, value, positive }: { label: string; value: string; positive: boolean }) {
  return (
    <div className="bg-surface-800 px-4 py-3">
      <p className="text-xs text-text-muted">{label}</p>
      <p className={`text-sm font-mono font-semibold ${positive ? 'text-accent-green' : 'text-accent-red'}`}>{value}</p>
    </div>
  )
}
