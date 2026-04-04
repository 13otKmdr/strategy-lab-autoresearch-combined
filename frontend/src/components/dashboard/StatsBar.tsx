import type { CycleSummary } from '../../types'
import MetricCard from '../shared/MetricCard'

export default function StatsBar({ cycle }: { cycle: CycleSummary | null }) {
  if (!cycle) return null
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 mb-6">
      <MetricCard label="Strategies" value={cycle.total_strategies} />
      <MetricCard label="Tests Run" value={cycle.total_tests} />
      <MetricCard
        label="Compliant"
        value={cycle.compliant_count}
        color="text-accent-green"
      />
      <MetricCard
        label="Non-Compliant"
        value={cycle.non_compliant_count}
        color="text-accent-red"
      />
      <MetricCard
        label="Best PF"
        value={cycle.best_profit_factor.toFixed(2)}
        color="text-accent-blue"
      />
      <MetricCard
        label="Best Return"
        value={`${(cycle.best_total_return * 100).toFixed(2)}%`}
        color="text-accent-purple"
      />
    </div>
  )
}
