import { useNavigate, useLocation } from 'react-router-dom'
import type { CycleSummary } from '../../types'
import { INSTRUMENTS, INSTRUMENT_NAMES, REGIME_COLORS, REGIME_LABELS } from '../../types'

export default function AssetTabs({ cycle }: { cycle: CycleSummary | null }) {
  const navigate = useNavigate()
  const location = useLocation()

  const isOverview = location.pathname === '/'
  const currentInstrument = location.pathname.startsWith('/asset/')
    ? location.pathname.split('/')[2]
    : null

  return (
    <div className="flex items-center gap-1 mb-6 overflow-x-auto pb-1">
      <button
        onClick={() => navigate('/')}
        className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors whitespace-nowrap ${
          isOverview
            ? 'bg-accent-blue/20 text-accent-blue border border-accent-blue/30'
            : 'text-text-secondary hover:text-text-primary hover:bg-surface-700'
        }`}
      >
        Overview
      </button>
      {INSTRUMENTS.map(inst => {
        const active = currentInstrument === inst
        const asset = cycle?.assets?.[inst]
        const regime = asset?.regime || ''
        const bestReturn = asset?.best_total_return || 0

        return (
          <button
            key={inst}
            onClick={() => navigate(`/asset/${inst}`)}
            className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors whitespace-nowrap ${
              active
                ? 'bg-accent-blue/20 text-accent-blue border border-accent-blue/30'
                : 'text-text-secondary hover:text-text-primary hover:bg-surface-700'
            }`}
          >
            <span className="font-semibold">{inst}</span>
            {asset && (
              <span className={`ml-2 text-xs ${bestReturn >= 0 ? 'text-accent-green' : 'text-accent-red'}`}>
                {bestReturn >= 0 ? '+' : ''}{(bestReturn * 100).toFixed(1)}%
              </span>
            )}
            {regime && (
              <span className={`ml-1 text-xs ${REGIME_COLORS[regime] || 'text-text-muted'}`}>
                {regime === 'trending_up' ? '↑' : regime === 'trending_down' ? '↓' : regime === 'volatile' ? '~' : '—'}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
