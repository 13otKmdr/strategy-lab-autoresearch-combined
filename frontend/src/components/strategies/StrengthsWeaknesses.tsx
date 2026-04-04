import { TrendingUp, TrendingDown } from 'lucide-react'

export default function StrengthsWeaknesses({ strengths, weaknesses }: {
  strengths: string[]
  weaknesses: string[]
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div className="bg-surface-800 border border-border rounded-lg p-4">
        <div className="flex items-center gap-2 mb-3">
          <TrendingUp className="w-4 h-4 text-accent-green" />
          <h3 className="text-sm font-medium text-accent-green">Strengths</h3>
        </div>
        {strengths.length > 0 ? (
          <ul className="space-y-2">
            {strengths.map((s, i) => (
              <li key={i} className="text-sm text-text-secondary flex items-start gap-2">
                <span className="text-accent-green mt-1">+</span>
                {s}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-text-muted">No notable strengths identified</p>
        )}
      </div>
      <div className="bg-surface-800 border border-border rounded-lg p-4">
        <div className="flex items-center gap-2 mb-3">
          <TrendingDown className="w-4 h-4 text-accent-red" />
          <h3 className="text-sm font-medium text-accent-red">Weaknesses</h3>
        </div>
        {weaknesses.length > 0 ? (
          <ul className="space-y-2">
            {weaknesses.map((w, i) => (
              <li key={i} className="text-sm text-text-secondary flex items-start gap-2">
                <span className="text-accent-red mt-1">-</span>
                {w}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-text-muted">No notable weaknesses identified</p>
        )}
      </div>
    </div>
  )
}
