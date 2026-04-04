import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'

export default function DrawdownChart({ dd025, dd050 }: {
  dd025: number[]
  dd050: number[]
}) {
  const maxLen = Math.max(dd025.length, dd050.length)
  const step = Math.max(1, Math.floor(maxLen / 500))

  const data = []
  for (let i = 0; i < maxLen; i += step) {
    data.push({
      bar: i,
      'DD 0.25%': dd025[i] ? -(dd025[i] * 100) : null,
      'DD 0.5%': dd050[i] ? -(dd050[i] * 100) : null,
    })
  }

  if (data.length === 0) {
    return <div className="text-center py-8 text-text-muted">No drawdown data available</div>
  }

  return (
    <div className="bg-surface-800 border border-border rounded-lg p-4">
      <h3 className="text-sm font-medium text-text-secondary mb-4">Drawdown Curve</h3>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis dataKey="bar" tick={{ fill: '#64748b', fontSize: 11 }} />
          <YAxis tick={{ fill: '#64748b', fontSize: 11 }} tickFormatter={(v) => `${v.toFixed(1)}%`} />
          <Tooltip
            contentStyle={{ backgroundColor: '#111118', border: '1px solid #1e293b', borderRadius: '8px' }}
            labelStyle={{ color: '#94a3b8' }}
            formatter={(value: number) => [`${value.toFixed(2)}%`, undefined]}
          />
          <Legend wrapperStyle={{ fontSize: 12, color: '#94a3b8' }} />
          <Area type="monotone" dataKey="DD 0.25%" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.15} strokeWidth={1.5} />
          <Area type="monotone" dataKey="DD 0.5%" stroke="#a855f7" fill="#a855f7" fillOpacity={0.15} strokeWidth={1.5} />
        </AreaChart>
      </ResponsiveContainer>
      {/* Compliance reference lines */}
      <div className="flex gap-4 mt-2 text-xs text-text-muted">
        <span className="text-accent-red">--- Futures limit: -4%</span>
        <span className="text-accent-amber">--- CFD limit: -8%</span>
      </div>
    </div>
  )
}
