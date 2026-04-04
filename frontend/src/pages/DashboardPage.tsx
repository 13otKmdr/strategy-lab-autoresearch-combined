import { useState, useEffect, useMemo, useCallback } from 'react'
import { Play, Loader2 } from 'lucide-react'
import type { CycleSummary, RankedStrategy, Filters } from '../types'
import { getCycles, runCycle } from '../api/client'
import StatsBar from '../components/dashboard/StatsBar'
import FilterBar from '../components/filters/FilterBar'
import StrategyTable from '../components/strategies/StrategyTable'
import Pagination from '../components/shared/Pagination'

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

export default function DashboardPage() {
  const [cycle, setCycle] = useState<CycleSummary | null>(null)
  const [loading, setLoading] = useState(false)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS)
  const [page, setPage] = useState(1)

  // Load most recent cycle on mount
  useEffect(() => {
    loadLatestCycle()
  }, [])

  async function loadLatestCycle() {
    setLoading(true)
    try {
      const cycles = await getCycles()
      if (cycles.length > 0) {
        setCycle(cycles[0])
      }
    } catch (e) {
      setError('Failed to load cycles')
    } finally {
      setLoading(false)
    }
  }

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

  const updateFilters = useCallback((partial: Partial<Filters>) => {
    setFilters(prev => ({ ...prev, ...partial }))
    setPage(1)
  }, [])

  // Filter and sort strategies
  const filtered = useMemo(() => {
    if (!cycle?.ranked_strategies) return []

    let list = [...cycle.ranked_strategies]

    // Search
    if (filters.search) {
      const q = filters.search.toLowerCase()
      list = list.filter(s =>
        s.strategy_name.toLowerCase().includes(q) ||
        s.strategy_type.toLowerCase().includes(q) ||
        s.instrument.toLowerCase().includes(q)
      )
    }

    // Strategy type
    if (filters.strategyType) {
      list = list.filter(s => s.strategy_type === filters.strategyType)
    }

    // Compliance
    if (filters.complianceOnly) {
      list = list.filter(s => s.overall_compliance === 'compliant')
    }

    // Sort
    list.sort((a, b) => {
      const field = filters.sortBy
      const aVal = (a as any)[field] ?? 0
      const bVal = (b as any)[field] ?? 0
      return filters.sortDir === 'desc' ? bVal - aVal : aVal - bVal
    })

    return list
  }, [cycle, filters])

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const pageStrategies = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">Strategy Dashboard</h2>
          {cycle && (
            <p className="text-sm text-text-muted mt-1">
              Cycle {cycle.cycle_id} &middot; {new Date(cycle.timestamp).toLocaleString()}
            </p>
          )}
        </div>
        <button
          onClick={handleRunCycle}
          disabled={running}
          className="flex items-center gap-2 px-5 py-2.5 bg-accent-blue text-white rounded-lg font-medium text-sm hover:bg-accent-blue/80 disabled:opacity-50 transition-colors"
        >
          {running ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Running Cycle...
            </>
          ) : (
            <>
              <Play className="w-4 h-4" />
              Run New Cycle
            </>
          )}
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-accent-red/10 border border-accent-red/30 rounded-lg text-sm text-accent-red">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-24">
          <Loader2 className="w-8 h-8 animate-spin text-accent-blue" />
        </div>
      ) : cycle ? (
        <>
          <StatsBar cycle={cycle} />
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
        </>
      ) : (
        <div className="text-center py-24">
          <p className="text-lg text-text-muted mb-4">No cycles yet. Run your first strategy generation cycle.</p>
          <button
            onClick={handleRunCycle}
            disabled={running}
            className="px-6 py-3 bg-accent-blue text-white rounded-lg font-medium hover:bg-accent-blue/80 transition-colors"
          >
            {running ? 'Running...' : 'Generate 50 Strategies'}
          </button>
        </div>
      )}
    </div>
  )
}
