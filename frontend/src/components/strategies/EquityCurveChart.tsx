import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'

export default function EquityCurveChart({ equity025, equity050 }: {
  equity025: number[]
  equity050: number[]
}) {
  const maxLen = Math.max(equity025.length, equity050.length)
  const step = Math.max(1, Math.floor(maxLen / 500))

  const data = []
  for (let i = 0; i < maxLen; i += step) {
    data.push({
      bar: i,
      'Risk 0.25%': equity025[i] ?? null,
      'Risk 0.5%': equity050[i] ?? null,
    })
  }

  if (data.length === 0) {
    return <div className="text-center py-8 text-text-muted">No equity data available</div>
  }

  return (
    <div className="bg-surface-800 border border-border rounded-lg p-4">
      <h3 className="text-sm font-medium text-text-secondary mb-4">Equity Curve</h3>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis dataKey="bar" tick={{ fill: '#64748b', fontSize: 11 }} />
          <YAxis tick={{ fill: '#64748b', fontSize: 11 }} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}K`} />
          <Tooltip
            contentStyle={{ backgroundColor: '#111118', border: '1px solid #1e293b', borderRadius: '8px' }}
            labelStyle={{ color: '#94a3b8' }}
            formatter={(value: number) => [`$${value.toFixed(0)}`, undefined]}
          />
          <Legend wrapperStyle={{ fontSize: 12, color: '#94a3b8' }} />
          <Line type="monotone" dataKey="Risk 0.25%" stroke="#3b82f6" strokeWidth={1.5} dot={false} />
          <Line type="monotone" dataKey="Risk 0.5%" stroke="#a855f7" strokeWidth={1.5} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
