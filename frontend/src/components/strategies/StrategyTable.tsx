import { useNavigate } from 'react-router-dom'
import type { RankedStrategy, Filters } from '../../types'
import ComplianceBadge from '../shared/ComplianceBadge'
import Badge from '../shared/Badge'

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

const TYPE_LABELS: Record<string, string> = {
  trend_following: 'Trend',
  mean_reversion: 'MeanRev',
  breakout: 'Breakout',
  momentum: 'Momentum',
  hybrid: 'Hybrid',
  orb: 'ORB',
  vwap_reversion: 'VWAP Rev',
  session_rotation: 'Session',
}

function fmt(n: number, decimals = 2): string {
  return n.toFixed(decimals)
}

function fmtPct(n: number): string {
  return `${(n * 100).toFixed(2)}%`
}

function fmtDollar(n: number): string {
  const sign = n >= 0 ? '+' : ''
  return `${sign}$${n.toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}`
}

export default function StrategyTable({ strategies, filters }: {
  strategies: RankedStrategy[]
  filters: Filters
}) {
  const navigate = useNavigate()
  const rv = filters.riskView

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-text-muted uppercase tracking-wider border-b border-border">
            <th className="px-4 py-3 w-12">#</th>
            <th className="px-4 py-3">Strategy</th>
            <th className="px-4 py-3">Type</th>
            <th className="px-4 py-3">Asset</th>
            <th className="px-4 py-3 text-right">Return %</th>
            <th className="px-4 py-3 text-right">Profit $</th>
            <th className="px-4 py-3 text-right">PF</th>
            <th className="px-4 py-3 text-right">Max DD</th>
            <th className="px-4 py-3 text-right">Win Rate</th>
            <th className="px-4 py-3 text-right">Trades</th>
            <th className="px-4 py-3 text-right">Score</th>
            <th className="px-4 py-3 text-right">Eval Pass</th>
            <th className="px-4 py-3 text-center">Compliance</th>
          </tr>
        </thead>
        <tbody>
          {strategies.map((s) => {
            const returnPct = rv === '025' ? s.total_return_pct_025 : s.total_return_pct_050
            const profit = rv === '025' ? s.net_profit_dollars_025 : s.net_profit_dollars_050
            const pf = rv === '025' ? s.profit_factor_025 : s.profit_factor_050
            const dd = rv === '025' ? s.max_drawdown_pct_025 : s.max_drawdown_pct_050
            const wr = rv === '025' ? s.win_rate_025 : s.win_rate_050
            const trades = rv === '025' ? s.total_trades_025 : s.total_trades_050
            const compliance = rv === '025' ? s.compliance_status_025 : s.compliance_status_050

            return (
              <tr
                key={s.strategy_id}
                onClick={() => navigate(`/strategy/${s.strategy_id}`)}
                className="border-b border-border/50 hover:bg-surface-800/80 cursor-pointer transition-colors"
              >
                <td className="px-4 py-3 text-text-muted font-mono">{s.rank}</td>
                <td className="px-4 py-3 font-medium">{s.strategy_name}</td>
                <td className="px-4 py-3">
                  <Badge variant={TYPE_COLORS[s.strategy_type] || 'muted'}>
                    {TYPE_LABELS[s.strategy_type] || s.strategy_type}
                  </Badge>
                </td>
                <td className="px-4 py-3 text-text-secondary font-mono">{s.instrument}</td>
                <td className={`px-4 py-3 text-right font-mono ${returnPct >= 0 ? 'text-accent-green' : 'text-accent-red'}`}>
                  {fmtPct(returnPct)}
                </td>
                <td className={`px-4 py-3 text-right font-mono ${profit >= 0 ? 'text-accent-green' : 'text-accent-red'}`}>
                  {fmtDollar(profit)}
                </td>
                <td className={`px-4 py-3 text-right font-mono ${pf >= 1.5 ? 'text-accent-green' : pf >= 1.0 ? 'text-accent-amber' : 'text-accent-red'}`}>
                  {pf === Infinity ? '∞' : fmt(pf)}
                </td>
                <td className={`px-4 py-3 text-right font-mono ${dd <= 0.04 ? 'text-accent-green' : 'text-accent-red'}`}>
                  {fmtPct(dd)}
                </td>
                <td className="px-4 py-3 text-right font-mono text-text-secondary">
                  {fmtPct(wr)}
                </td>
                <td className="px-4 py-3 text-right font-mono text-text-secondary">
                  {trades}
                </td>
                <td className="px-4 py-3 text-right">
                  <span className={`font-semibold font-mono ${s.composite_score >= 50 ? 'text-accent-green' : s.composite_score >= 25 ? 'text-accent-amber' : 'text-accent-red'}`}>
                    {fmt(s.composite_score, 1)}
                  </span>
                </td>
                <td className="px-4 py-3 text-right">
                  {s.eval_pass_rate > 0 ? (
                    <span className={`font-mono text-sm ${s.eval_pass_rate >= 0.7 ? 'text-accent-green' : s.eval_pass_rate >= 0.4 ? 'text-accent-amber' : 'text-accent-red'}`}>
                      {(s.eval_pass_rate * 100).toFixed(0)}%
                    </span>
                  ) : (
                    <span className="text-text-muted text-xs">--</span>
                  )}
                </td>
                <td className="px-4 py-3 text-center">
                  <ComplianceBadge status={compliance} />
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {strategies.length === 0 && (
        <div className="text-center py-12 text-text-muted">
          No strategies match the current filters.
        </div>
      )}
    </div>
  )
}
