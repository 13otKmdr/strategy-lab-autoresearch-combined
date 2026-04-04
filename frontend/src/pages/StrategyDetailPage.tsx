import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Loader2, AlertTriangle } from 'lucide-react'
import type { StrategyDetail } from '../types'
import { getStrategyDetail } from '../api/client'
import Badge from '../components/shared/Badge'
import ChartToggle from '../components/shared/ChartToggle'
import ComparisonPanel from '../components/strategies/ComparisonPanel'
import LightweightChart, { equityCurveToChartData } from '../components/charts/LightweightChart'
import StrengthsWeaknesses from '../components/strategies/StrengthsWeaknesses'

const TYPE_COLORS: Record<string, string> = {
  trend_following: 'blue',
  mean_reversion: 'purple',
  breakout: 'amber',
  momentum: 'green',
  hybrid: 'muted',
  orb: 'red',
  vwap_reversion: 'blue',
  session_rotation: 'purple',
}

export default function StrategyDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [detail, setDetail] = useState<StrategyDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [chartMode, setChartMode] = useState<'dollar' | 'percent'>('dollar')

  useEffect(() => {
    if (!id) return
    setLoading(true)
    getStrategyDetail(id)
      .then(setDetail)
      .catch(() => setError('Failed to load strategy'))
      .finally(() => setLoading(false))
  }, [id])

  if (loading) {
    return <div className="flex items-center justify-center py-24"><Loader2 className="w-8 h-8 animate-spin text-accent-blue" /></div>
  }

  if (error || !detail) {
    return (
      <div className="text-center py-24">
        <p className="text-accent-red mb-4">{error || 'Strategy not found'}</p>
        <button onClick={() => navigate(-1)} className="text-accent-blue hover:underline">Go Back</button>
      </div>
    )
  }

  const { strategy, result_025, result_050, equity_data, strengths, weaknesses } = detail
  const hasOOS = result_025?.oos_total_trades > 0 || result_050?.oos_total_trades > 0

  // Check for overfit warning
  const isOverfit = result_025 && result_050 && (
    (result_025.profit_factor > 1.5 && result_025.oos_profit_factor > 0 && result_025.oos_profit_factor < result_025.profit_factor * 0.5) ||
    (result_025.sharpe_ratio > 1.0 && result_025.oos_sharpe_ratio < 0)
  )

  const eq025 = equity_data?.equity_curve_025 || []
  const eq050 = equity_data?.equity_curve_050 || []
  const dd025 = equity_data?.drawdown_curve_025 || []
  const dd050 = equity_data?.drawdown_curve_050 || []

  return (
    <div className="space-y-6">
      {/* Back + Header */}
      <div>
        <button onClick={() => navigate(-1)} className="flex items-center gap-1 text-sm text-text-muted hover:text-text-primary transition-colors mb-4">
          <ArrowLeft className="w-4 h-4" /> Back
        </button>
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <h2 className="text-2xl font-bold">{strategy.strategy_name}</h2>
              <Badge variant={TYPE_COLORS[strategy.strategy_type] || 'muted'}>
                {strategy.strategy_type.replace('_', ' ')}
              </Badge>
            </div>
            <p className="text-sm text-text-secondary max-w-2xl">{strategy.thesis_summary}</p>
          </div>
          <div className="text-right">
            <p className="text-xs text-text-muted uppercase tracking-wider mb-1">Instrument</p>
            <p className="text-sm font-mono">{strategy.intended_asset_classes?.join(', ')}</p>
          </div>
        </div>
      </div>

      {/* Overfit Warning */}
      {isOverfit && (
        <div className="flex items-center gap-3 p-4 bg-accent-amber/10 border border-accent-amber/30 rounded-lg">
          <AlertTriangle className="w-5 h-5 text-accent-amber flex-shrink-0" />
          <div>
            <p className="text-sm font-medium text-accent-amber">Potential Overfit Detected</p>
            <p className="text-xs text-text-secondary mt-1">
              This strategy performs significantly worse on out-of-sample data than in-sample. The in-sample results may not be repeatable in live trading.
            </p>
          </div>
        </div>
      )}

      {/* Strategy Logic Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <InfoCard title="Indicators">
          {strategy.indicators_used?.map((ind, i) => (
            <p key={i} className="text-sm text-text-secondary">
              {ind.type} ({Object.entries(ind.params || {}).map(([k, v]) => `${k}: ${v}`).join(', ') || 'default'})
            </p>
          ))}
        </InfoCard>
        <InfoCard title="Entry Rules">
          {strategy.strategy_type === 'orb' ? (
            <>
              <p className="text-sm text-text-secondary">Trigger: ORB Breakout</p>
              {strategy.entry_rules?.range_minutes && <p className="text-sm text-text-secondary">Range: {strategy.entry_rules.range_minutes} min</p>}
              {strategy.entry_rules?.breakout_buffer && <p className="text-sm text-text-secondary">Buffer: {String(strategy.entry_rules.breakout_buffer)} ATR</p>}
              {strategy.entry_rules?.direction && <p className="text-sm text-text-secondary">Direction: {String(strategy.entry_rules.direction)}</p>}
            </>
          ) : strategy.strategy_type === 'vwap_reversion' ? (
            <>
              <p className="text-sm text-text-secondary">Trigger: VWAP Reversion</p>
              {strategy.entry_rules?.distance_threshold_atr && <p className="text-sm text-text-secondary">Distance: {String(strategy.entry_rules.distance_threshold_atr)} ATR</p>}
              {strategy.entry_rules?.direction && <p className="text-sm text-text-secondary">Direction: {String(strategy.entry_rules.direction)}</p>}
            </>
          ) : strategy.strategy_type === 'session_rotation' ? (
            <>
              <p className="text-sm text-text-secondary">Session Rotation Engine</p>
              {strategy.entry_rules?.morning && <p className="text-sm text-text-secondary">Morning: {String((strategy.entry_rules.morning as any)?.trigger || 'default')}</p>}
              {strategy.entry_rules?.midday && <p className="text-sm text-text-secondary">Midday: {String((strategy.entry_rules.midday as any)?.trigger || 'default')}</p>}
              {strategy.entry_rules?.afternoon && <p className="text-sm text-text-secondary">Afternoon: {String((strategy.entry_rules.afternoon as any)?.trigger || 'default')}</p>}
            </>
          ) : (
            <p className="text-sm text-text-secondary">{strategy.entry_rules?.description || JSON.stringify(strategy.entry_rules)}</p>
          )}
        </InfoCard>
        <InfoCard title="Exit Rules">
          <p className="text-sm text-text-secondary">Stop: {strategy.stop_loss_logic?.type} ({String(strategy.stop_loss_logic?.value)})</p>
          <p className="text-sm text-text-secondary">Target: {strategy.take_profit_logic?.type} ({String(strategy.take_profit_logic?.value)})</p>
          {strategy.trailing_stop_or_break_even_logic?.type !== 'none' && (
            <p className="text-sm text-text-secondary">Trailing: {strategy.trailing_stop_or_break_even_logic?.type} ({String(strategy.trailing_stop_or_break_even_logic?.value)})</p>
          )}
        </InfoCard>
        <InfoCard title="Session">
          <p className="text-sm text-text-secondary">{(strategy.session_filters as any)?.description || 'All sessions'}</p>
        </InfoCard>
        <InfoCard title="Volatility">
          <p className="text-sm text-text-secondary">{(strategy.volatility_filters as any)?.description || 'No filter'}</p>
        </InfoCard>
        <InfoCard title="Timeframe">
          <p className="text-sm text-text-secondary">{strategy.timeframe_stack?.join(', ') || '15min'}</p>
        </InfoCard>
      </div>

      {/* IS/OOS Comparison */}
      <ComparisonPanel r025={result_025} r050={result_050} showOOS={hasOOS} />

      {/* Charts */}
      <div className="flex justify-end">
        <ChartToggle mode={chartMode} onChange={setChartMode} />
      </div>

      {eq025.length > 0 && (
        <LightweightChart
          data025={equityCurveToChartData(eq025, chartMode)}
          data050={equityCurveToChartData(eq050, chartMode)}
          mode={chartMode}
          height={350}
          title={chartMode === 'dollar' ? 'Equity Curve ($)' : 'Account Growth (%)'}
        />
      )}

      {dd025.length > 0 && (
        <LightweightChart
          data025={equityCurveToChartData(dd025.map(d => -d * 100), 'dollar')}
          data050={equityCurveToChartData(dd050.map(d => -d * 100), 'dollar')}
          mode="dollar"
          height={200}
          title="Drawdown (%)"
          type="area"
        />
      )}

      {/* Strengths & Weaknesses */}
      <StrengthsWeaknesses strengths={strengths || []} weaknesses={weaknesses || []} />

      {/* Monthly Returns */}
      {result_025?.monthly_returns && result_025.monthly_returns.length > 0 && (
        <div className="bg-surface-800 border border-border rounded-lg p-4">
          <h3 className="text-sm font-medium text-text-secondary mb-3">Monthly Returns (0.25% Risk)</h3>
          <div className="flex flex-wrap gap-2">
            {result_025.monthly_returns.map((m, i) => (
              <div key={i} className={`px-3 py-2 rounded-md text-xs font-mono ${
                m.return_pct >= 0 ? 'bg-accent-green/10 text-accent-green' : 'bg-accent-red/10 text-accent-red'
              }`}>
                <div className="text-text-muted">{m.month}</div>
                <div>{(m.return_pct * 100).toFixed(2)}%</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function InfoCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-surface-800 border border-border rounded-lg p-4">
      <h4 className="text-xs text-text-muted uppercase tracking-wider mb-2">{title}</h4>
      <div className="space-y-1">{children}</div>
    </div>
  )
}
