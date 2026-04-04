import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Play, Loader2, TrendingUp, TrendingDown, Activity, Zap, Briefcase } from 'lucide-react'
import type { CycleSummary } from '../types'
import { INSTRUMENTS, INSTRUMENT_NAMES, REGIME_COLORS, REGIME_LABELS } from '../types'
import { getCycles, runCycle } from '../api/client'
import MetricCard from '../components/shared/MetricCard'
import ComplianceBadge from '../components/shared/ComplianceBadge'
import Badge from '../components/shared/Badge'

export default function OverviewPage({ cycle, setCycle, running, setRunning }: {
  cycle: CycleSummary | null
  setCycle: (c: CycleSummary) => void
  running: boolean
  setRunning: (r: boolean) => void
}) {
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)

  async function handleRunCycle() {
    setRunning(true)
    setError(null)
    try {
      const result = await runCycle()
      setCycle(result)
    } catch (e) {
      setError('Cycle failed — check backend logs')
    } finally {
      setRunning(false)
    }
  }

  if (!cycle) {
    return (
      <div className="text-center py-24">
        <Activity className="w-12 h-12 text-accent-blue mx-auto mb-4" />
        <p className="text-lg text-text-muted mb-4">No cycles yet. Run your first intelligence-first cycle.</p>
        <button
          onClick={handleRunCycle}
          disabled={running}
          className="px-6 py-3 bg-accent-blue text-white rounded-lg font-medium hover:bg-accent-blue/80 transition-colors"
        >
          {running ? 'Running (~5 min)...' : 'Scout & Generate Strategies'}
        </button>
        {error && <p className="mt-4 text-accent-red text-sm">{error}</p>}
      </div>
    )
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">Strategy Research Overview</h2>
          <p className="text-sm text-text-muted mt-1">
            Cycle {cycle.cycle_id} &middot; {new Date(cycle.timestamp).toLocaleString()}
            {cycle.totals?.elapsed_seconds && ` &middot; ${cycle.totals.elapsed_seconds}s`}
          </p>
        </div>
        <button
          onClick={handleRunCycle}
          disabled={running}
          className="flex items-center gap-2 px-5 py-2.5 bg-accent-blue text-white rounded-lg font-medium text-sm hover:bg-accent-blue/80 disabled:opacity-50 transition-colors"
        >
          {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
          {running ? 'Running Cycle...' : 'New Cycle'}
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-accent-red/10 border border-accent-red/30 rounded-lg text-sm text-accent-red">{error}</div>
      )}

      {/* Global stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 mb-8">
        <MetricCard label="Total Strategies" value={cycle.total_strategies} />
        <MetricCard label="Total Tests" value={cycle.total_tests} />
        <MetricCard label="Compliant" value={cycle.compliant_count} color="text-accent-green" />
        <MetricCard label="Non-Compliant" value={cycle.non_compliant_count} color="text-accent-red" />
        <MetricCard label="Best PF" value={cycle.best_profit_factor.toFixed(2)} color="text-accent-blue" />
        <MetricCard label="Best Return" value={`${(cycle.best_total_return * 100).toFixed(2)}%`} color="text-accent-purple" />
      </div>

      {/* Per-asset cards */}
      <h3 className="text-lg font-semibold mb-4">Per-Asset Results</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {INSTRUMENTS.map(inst => {
          const asset = cycle.assets?.[inst]
          if (!asset) return null

          const regimeColor = REGIME_COLORS[asset.regime] || 'text-text-muted'
          const regimeLabel = REGIME_LABELS[asset.regime] || asset.regime

          return (
            <div
              key={inst}
              onClick={() => navigate(`/asset/${inst}`)}
              className="bg-surface-800 border border-border rounded-lg p-5 cursor-pointer hover:border-accent-blue/50 transition-colors"
            >
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h4 className="text-lg font-semibold">{inst}</h4>
                  <p className="text-xs text-text-muted">{INSTRUMENT_NAMES[inst]}</p>
                </div>
                <div className="text-right">
                  <span className={`text-sm font-medium ${regimeColor}`}>{regimeLabel}</span>
                  <p className="text-xs text-text-muted">{asset.direction_bias}</p>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3 mb-3">
                <div>
                  <p className="text-xs text-text-muted">Strategies</p>
                  <p className="text-sm font-semibold">{asset.total_strategies}</p>
                </div>
                <div>
                  <p className="text-xs text-text-muted">Compliant</p>
                  <p className="text-sm font-semibold text-accent-green">{asset.compliant_count}</p>
                </div>
                <div>
                  <p className="text-xs text-text-muted">Avg Score</p>
                  <p className="text-sm font-semibold">{asset.avg_composite_score.toFixed(1)}</p>
                </div>
              </div>

              <div className="flex items-center justify-between pt-3 border-t border-border/50">
                <div>
                  <p className="text-xs text-text-muted">Best Strategy</p>
                  <p className="text-sm font-medium truncate max-w-[180px]">{asset.best_strategy_name || '—'}</p>
                </div>
                <div className="text-right">
                  <p className="text-xs text-text-muted">Best Return</p>
                  <p className={`text-sm font-mono font-semibold ${asset.best_total_return >= 0 ? 'text-accent-green' : 'text-accent-red'}`}>
                    {(asset.best_total_return * 100).toFixed(2)}%
                  </p>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Recommended Portfolio */}
      {cycle.portfolio && cycle.portfolio.strategies && cycle.portfolio.strategies.length > 0 && (
        <div className="mt-8">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Briefcase className="w-5 h-5 text-accent-blue" />
            Recommended Portfolio
          </h3>
          <div className="bg-surface-800 border border-border rounded-lg p-5">
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 mb-5">
              <MetricCard label="Combined Return" value={`${(cycle.portfolio.combined_return_pct * 100).toFixed(2)}%`} color="text-accent-green" />
              <MetricCard label="Combined Profit" value={`$${cycle.portfolio.combined_net_profit.toFixed(0)}`} color="text-accent-green" />
              <MetricCard label="Profit Factor" value={cycle.portfolio.combined_profit_factor.toFixed(2)} color="text-accent-blue" />
              <MetricCard label="Sharpe Ratio" value={cycle.portfolio.combined_sharpe.toFixed(2)} color="text-accent-blue" />
              <MetricCard label="Max Drawdown" value={`${(cycle.portfolio.combined_max_dd_pct * 100).toFixed(2)}%`} color="text-accent-red" />
              <MetricCard label="Diversification" value={`${(cycle.portfolio.diversification_score * 100).toFixed(0)}%`} color="text-accent-purple" />
            </div>
            <div className="space-y-2">
              {cycle.portfolio.strategies.map((ps, i) => (
                <div key={i} className="flex items-center justify-between py-2 px-3 bg-surface-700/50 rounded-md">
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-text-muted font-mono">#{i + 1}</span>
                    <span className="text-sm font-medium">{ps.name}</span>
                    <Badge variant="muted">{ps.instrument}</Badge>
                  </div>
                  <span className="text-sm font-mono text-accent-blue">{(ps.weight * 100).toFixed(0)}% weight</span>
                </div>
              ))}
            </div>
            <ComplianceBadge status={cycle.portfolio.compliance_status} />
          </div>
        </div>
      )}
    </div>
  )
}
