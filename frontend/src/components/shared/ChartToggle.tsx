import { DollarSign, Percent } from 'lucide-react'

export default function ChartToggle({ mode, onChange }: {
  mode: 'dollar' | 'percent'
  onChange: (mode: 'dollar' | 'percent') => void
}) {
  return (
    <div className="flex bg-surface-700 border border-border rounded-md overflow-hidden">
      <button
        onClick={() => onChange('dollar')}
        className={`flex items-center gap-1 px-3 py-1.5 text-xs font-medium transition-colors ${
          mode === 'dollar' ? 'bg-accent-blue/20 text-accent-blue' : 'text-text-secondary hover:text-text-primary'
        }`}
      >
        <DollarSign className="w-3 h-3" />
        Dollar
      </button>
      <button
        onClick={() => onChange('percent')}
        className={`flex items-center gap-1 px-3 py-1.5 text-xs font-medium transition-colors ${
          mode === 'percent' ? 'bg-accent-blue/20 text-accent-blue' : 'text-text-secondary hover:text-text-primary'
        }`}
      >
        <Percent className="w-3 h-3" />
        Percent
      </button>
    </div>
  )
}
