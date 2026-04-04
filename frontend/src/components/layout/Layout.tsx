import type { ReactNode } from 'react'
import { Activity } from 'lucide-react'

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-surface-900 text-text-primary">
      <header className="border-b border-border bg-surface-800/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-[1600px] mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Activity className="w-6 h-6 text-accent-blue" />
            <h1 className="text-lg font-semibold tracking-tight">StrategyLab</h1>
            <span className="text-xs text-text-muted bg-surface-700 px-2 py-0.5 rounded-full">v1.0</span>
          </div>
          <div className="flex items-center gap-4 text-sm text-text-secondary">
            <span>Micro Futures</span>
            <span className="text-text-muted">|</span>
            <span>15m Timeframe</span>
            <span className="text-text-muted">|</span>
            <span>$50K Capital</span>
          </div>
        </div>
      </header>
      <main className="max-w-[1600px] mx-auto px-6 py-6">
        {children}
      </main>
    </div>
  )
}
