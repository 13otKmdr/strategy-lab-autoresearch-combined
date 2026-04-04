const variants: Record<string, string> = {
  green: 'bg-accent-green/15 text-accent-green border-accent-green/30',
  red: 'bg-accent-red/15 text-accent-red border-accent-red/30',
  blue: 'bg-accent-blue/15 text-accent-blue border-accent-blue/30',
  amber: 'bg-accent-amber/15 text-accent-amber border-accent-amber/30',
  purple: 'bg-accent-purple/15 text-accent-purple border-accent-purple/30',
  muted: 'bg-surface-600/50 text-text-secondary border-surface-500/30',
}

export default function Badge({ children, variant = 'muted' }: { children: React.ReactNode; variant?: string }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-md border ${variants[variant] || variants.muted}`}>
      {children}
    </span>
  )
}
