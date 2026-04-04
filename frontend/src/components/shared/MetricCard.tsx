export default function MetricCard({ label, value, subtext, color }: {
  label: string
  value: string | number
  subtext?: string
  color?: string
}) {
  const textColor = color || 'text-text-primary'
  return (
    <div className="bg-surface-800 border border-border rounded-lg p-4">
      <p className="text-xs text-text-muted uppercase tracking-wider mb-1">{label}</p>
      <p className={`text-2xl font-semibold ${textColor}`}>{value}</p>
      {subtext && <p className="text-xs text-text-secondary mt-1">{subtext}</p>}
    </div>
  )
}
