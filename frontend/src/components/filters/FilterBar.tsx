import { Search } from 'lucide-react'
import type { Filters, SortField } from '../../types'

const STRATEGY_TYPES = [
  { value: '', label: 'All Types' },
  { value: 'trend_following', label: 'Trend Following' },
  { value: 'mean_reversion', label: 'Mean Reversion' },
  { value: 'breakout', label: 'Breakout' },
  { value: 'momentum', label: 'Momentum' },
  { value: 'hybrid', label: 'Hybrid' },
  { value: 'orb', label: 'ORB' },
  { value: 'vwap_reversion', label: 'VWAP Reversion' },
  { value: 'session_rotation', label: 'Session Rotation' },
]

const SORT_OPTIONS: { value: SortField; label: string }[] = [
  { value: 'composite_score', label: 'Score' },
  { value: 'profit_factor_025', label: 'PF (0.25%)' },
  { value: 'profit_factor_050', label: 'PF (0.5%)' },
  { value: 'net_profit_dollars_025', label: 'Profit $ (0.25%)' },
  { value: 'net_profit_dollars_050', label: 'Profit $ (0.5%)' },
  { value: 'total_return_pct_025', label: 'Return % (0.25%)' },
  { value: 'win_rate_025', label: 'Win Rate (0.25%)' },
  { value: 'max_drawdown_pct_025', label: 'Drawdown (0.25%)' },
]

export default function FilterBar({ filters, onChange }: {
  filters: Filters
  onChange: (f: Partial<Filters>) => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 mb-4 p-4 bg-surface-800 border border-border rounded-lg">
      {/* Search */}
      <div className="relative flex-1 min-w-[200px]">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
        <input
          type="text"
          placeholder="Search strategies..."
          value={filters.search}
          onChange={e => onChange({ search: e.target.value })}
          className="w-full pl-9 pr-3 py-2 bg-surface-700 border border-border rounded-md text-sm text-text-primary placeholder-text-muted focus:outline-none focus:ring-1 focus:ring-accent-blue"
        />
      </div>

      {/* Strategy Type */}
      <select
        value={filters.strategyType}
        onChange={e => onChange({ strategyType: e.target.value })}
        className="px-3 py-2 bg-surface-700 border border-border rounded-md text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-accent-blue"
      >
        {STRATEGY_TYPES.map(t => (
          <option key={t.value} value={t.value}>{t.label}</option>
        ))}
      </select>

      {/* Compliance Toggle */}
      <label className="flex items-center gap-2 px-3 py-2 bg-surface-700 border border-border rounded-md text-sm cursor-pointer">
        <input
          type="checkbox"
          checked={filters.complianceOnly}
          onChange={e => onChange({ complianceOnly: e.target.checked })}
          className="accent-accent-green"
        />
        <span className="text-text-secondary">Compliant Only</span>
      </label>

      {/* Risk View Toggle */}
      <div className="flex bg-surface-700 border border-border rounded-md overflow-hidden">
        <button
          onClick={() => onChange({ riskView: '025' })}
          className={`px-3 py-2 text-sm transition-colors ${filters.riskView === '025' ? 'bg-accent-blue/20 text-accent-blue' : 'text-text-secondary hover:text-text-primary'}`}
        >
          0.25%
        </button>
        <button
          onClick={() => onChange({ riskView: '050' })}
          className={`px-3 py-2 text-sm transition-colors ${filters.riskView === '050' ? 'bg-accent-blue/20 text-accent-blue' : 'text-text-secondary hover:text-text-primary'}`}
        >
          0.5%
        </button>
      </div>

      {/* Sort */}
      <select
        value={filters.sortBy}
        onChange={e => onChange({ sortBy: e.target.value as SortField })}
        className="px-3 py-2 bg-surface-700 border border-border rounded-md text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-accent-blue"
      >
        {SORT_OPTIONS.map(s => (
          <option key={s.value} value={s.value}>{s.label}</option>
        ))}
      </select>

      {/* Sort Direction */}
      <button
        onClick={() => onChange({ sortDir: filters.sortDir === 'desc' ? 'asc' : 'desc' })}
        className="px-3 py-2 bg-surface-700 border border-border rounded-md text-sm text-text-secondary hover:text-text-primary transition-colors"
      >
        {filters.sortDir === 'desc' ? '↓ Desc' : '↑ Asc'}
      </button>
    </div>
  )
}
