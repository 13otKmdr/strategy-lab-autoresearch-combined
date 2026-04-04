import type { BacktestResult } from '../../types'
import ComplianceBadge from '../shared/ComplianceBadge'

function fmtPct(n: number): string {
  return `${(n * 100).toFixed(2)}%`
}

function fmtDollar(n: number): string {
  const sign = n >= 0 ? '+' : ''
  return `${sign}$${n.toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}`
}

function Row({ label, val025, val050, format = 'text', highlight }: {
  label: string
  val025: number | string
  val050: number | string
  format?: 'text' | 'pct' | 'dollar' | 'pf'
  highlight?: 'positive' | 'negative' | 'none'
}) {
  const fmt = (v: number | string) => {
    if (typeof v === 'string') return v
    switch (format) {
      case 'pct': return fmtPct(v)
      case 'dollar': return fmtDollar(v)
      case 'pf': return v === Infinity ? '∞' : v.toFixed(2)
      default: return String(v)
    }
  }

  const color = (v: number | string) => {
    if (highlight === 'none' || typeof v === 'string') return 'text-text-primary'
    if (highlight === 'positive') return Number(v) >= 0 ? 'text-accent-green' : 'text-accent-red'
    if (highlight === 'negative') return Number(v) <= 0.04 ? 'text-accent-green' : 'text-accent-red'
    return 'text-text-primary'
  }

  return (
    <tr className="border-b border-border/30">
      <td className="py-2 pr-4 text-text-muted text-sm">{label}</td>
      <td className={`py-2 px-4 text-right font-mono text-sm ${color(val025)}`}>{fmt(val025)}</td>
      <td className={`py-2 pl-4 text-right font-mono text-sm ${color(val050)}`}>{fmt(val050)}</td>
    </tr>
  )
}

export default function ComparisonPanel({ r025, r050, showOOS = false }: {
  r025: BacktestResult | null
  r050: BacktestResult | null
  showOOS?: boolean
}) {
  if (!r025 || !r050) return <div className="text-text-muted">No comparison data</div>

  return (
    <div className="space-y-4">
      {/* IS Results */}
      <div className="bg-surface-800 border border-border rounded-lg p-4">
        <h3 className="text-sm font-medium text-text-secondary mb-4">
          {showOOS ? 'In-Sample Results (18 months)' : 'Risk Level Comparison'}
        </h3>
        <table className="w-full">
          <thead>
            <tr className="border-b border-border text-xs text-text-muted uppercase tracking-wider">
              <th className="py-2 pr-4 text-left">Metric</th>
              <th className="py-2 px-4 text-right">0.25% Risk</th>
              <th className="py-2 pl-4 text-right">0.5% Risk</th>
            </tr>
          </thead>
          <tbody>
            <Row label="Total Return" val025={r025.total_return_pct} val050={r050.total_return_pct} format="pct" highlight="positive" />
            <Row label="Net Profit" val025={r025.net_profit_dollars} val050={r050.net_profit_dollars} format="dollar" highlight="positive" />
            <Row label="Profit Factor" val025={r025.profit_factor} val050={r050.profit_factor} format="pf" />
            <Row label="Win Rate" val025={r025.win_rate} val050={r050.win_rate} format="pct" />
            <Row label="Avg R-Multiple" val025={r025.avg_r_multiple} val050={r050.avg_r_multiple} format="text" />
            <Row label="Max Drawdown" val025={r025.max_drawdown_pct} val050={r050.max_drawdown_pct} format="pct" highlight="negative" />
            <Row label="Max DD $" val025={r025.max_drawdown_dollars} val050={r050.max_drawdown_dollars} format="dollar" />
            <Row label="Sharpe Ratio" val025={r025.sharpe_ratio} val050={r050.sharpe_ratio} format="text" />
            <Row label="Sortino Ratio" val025={r025.sortino_ratio} val050={r050.sortino_ratio} format="text" />
            <Row label="Total Trades" val025={r025.total_trades} val050={r050.total_trades} format="text" />
            <Row label="Best Trade" val025={r025.best_trade} val050={r050.best_trade} format="dollar" />
            <Row label="Worst Trade" val025={r025.worst_trade} val050={r050.worst_trade} format="dollar" />
            <tr className="border-b border-border/30">
              <td className="py-2 pr-4 text-text-muted text-sm">Compliance</td>
              <td className="py-2 px-4 text-right"><ComplianceBadge status={r025.compliance_status} /></td>
              <td className="py-2 pl-4 text-right"><ComplianceBadge status={r050.compliance_status} /></td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* OOS Results */}
      {showOOS && (r025.oos_total_trades > 0 || r050.oos_total_trades > 0) && (
        <div className="bg-surface-800 border border-border rounded-lg p-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium text-text-secondary">Out-of-Sample Validation (6 months)</h3>
            {_isOverfit(r025, r050) && (
              <span className="px-2 py-1 text-xs font-medium bg-accent-red/15 text-accent-red rounded-md border border-accent-red/30">
                Potential Overfit Detected
              </span>
            )}
          </div>
          <table className="w-full">
            <thead>
              <tr className="border-b border-border text-xs text-text-muted uppercase tracking-wider">
                <th className="py-2 pr-4 text-left">OOS Metric</th>
                <th className="py-2 px-4 text-right">0.25% Risk</th>
                <th className="py-2 pl-4 text-right">0.5% Risk</th>
              </tr>
            </thead>
            <tbody>
              <Row label="OOS Return" val025={r025.oos_total_return_pct} val050={r050.oos_total_return_pct} format="pct" highlight="positive" />
              <Row label="OOS Profit Factor" val025={r025.oos_profit_factor} val050={r050.oos_profit_factor} format="pf" />
              <Row label="OOS Sharpe" val025={r025.oos_sharpe_ratio} val050={r050.oos_sharpe_ratio} format="text" />
              <Row label="OOS Max DD" val025={r025.oos_max_drawdown_pct} val050={r050.oos_max_drawdown_pct} format="pct" highlight="negative" />
              <Row label="OOS Trades" val025={r025.oos_total_trades} val050={r050.oos_total_trades} format="text" />
              <Row label="OOS Win Rate" val025={r025.oos_win_rate} val050={r050.oos_win_rate} format="pct" />
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function _isOverfit(r025: BacktestResult, r050: BacktestResult): boolean {
  // Check if IS performance significantly exceeds OOS
  for (const r of [r025, r050]) {
    if (r.profit_factor > 1.5 && r.oos_profit_factor > 0 && r.oos_profit_factor < r.profit_factor * 0.5) {
      return true
    }
    if (r.sharpe_ratio > 1.0 && r.oos_sharpe_ratio < 0) {
      return true
    }
  }
  return false
}
