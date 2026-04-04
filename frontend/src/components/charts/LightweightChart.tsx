import { useEffect, useRef } from 'react'
import { createChart, type IChartApi, type ISeriesApi, ColorType } from 'lightweight-charts'

interface ChartDataPoint {
  time: string;  // YYYY-MM-DD or Unix timestamp
  value: number;
}

interface LightweightChartProps {
  data025: ChartDataPoint[];
  data050: ChartDataPoint[];
  mode: 'dollar' | 'percent';
  height?: number;
  title?: string;
  type?: 'line' | 'area';
}

export default function LightweightChart({
  data025,
  data050,
  mode,
  height = 300,
  title,
  type = 'line',
}: LightweightChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: '#111118' },
        textColor: '#64748b',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: '#1e293b' },
        horzLines: { color: '#1e293b' },
      },
      crosshair: {
        vertLine: { color: '#3b82f6', width: 1, style: 2 },
        horzLine: { color: '#3b82f6', width: 1, style: 2 },
      },
      rightPriceScale: {
        borderColor: '#1e293b',
      },
      timeScale: {
        borderColor: '#1e293b',
        timeVisible: false,
      },
    })
    chartRef.current = chart

    // Series for 0.25% risk
    if (data025.length > 0) {
      if (type === 'area') {
        const series = chart.addAreaSeries({
          lineColor: '#3b82f6',
          topColor: 'rgba(59, 130, 246, 0.2)',
          bottomColor: 'rgba(59, 130, 246, 0.02)',
          lineWidth: 2,
          title: '0.25% Risk',
        })
        series.setData(data025 as any)
      } else {
        const series = chart.addLineSeries({
          color: '#3b82f6',
          lineWidth: 2,
          title: '0.25% Risk',
        })
        series.setData(data025 as any)
      }
    }

    // Series for 0.5% risk
    if (data050.length > 0) {
      if (type === 'area') {
        const series = chart.addAreaSeries({
          lineColor: '#a855f7',
          topColor: 'rgba(168, 85, 247, 0.2)',
          bottomColor: 'rgba(168, 85, 247, 0.02)',
          lineWidth: 2,
          title: '0.5% Risk',
        })
        series.setData(data050 as any)
      } else {
        const series = chart.addLineSeries({
          color: '#a855f7',
          lineWidth: 2,
          title: '0.5% Risk',
        })
        series.setData(data050 as any)
      }
    }

    chart.timeScale().fitContent()

    // Resize handler
    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
    }
  }, [data025, data050, mode, height, type])

  return (
    <div className="bg-surface-800 border border-border rounded-lg p-4">
      {title && <h3 className="text-sm font-medium text-text-secondary mb-3">{title}</h3>}
      <div ref={containerRef} />
      <div className="flex gap-4 mt-2 text-xs text-text-muted">
        <span className="flex items-center gap-1">
          <span className="w-3 h-0.5 bg-accent-blue inline-block" /> 0.25% Risk
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-0.5 bg-accent-purple inline-block" /> 0.5% Risk
        </span>
      </div>
    </div>
  )
}

/**
 * Convert an equity curve array to chart data points.
 * Uses index as time (bar number) since we don't have timestamps for each bar.
 */
export function equityCurveToChartData(curve: number[], mode: 'dollar' | 'percent', initialCapital: number = 50000): ChartDataPoint[] {
  if (!curve || curve.length === 0) return []
  const step = Math.max(1, Math.floor(curve.length / 1000)) // downsample to 1000 points max
  const baseDate = new Date('2024-04-03')
  const data: ChartDataPoint[] = []
  for (let i = 0; i < curve.length; i += step) {
    const d = new Date(baseDate)
    d.setDate(d.getDate() + Math.floor(i / 26)) // ~26 bars per day
    const time = d.toISOString().split('T')[0]
    const value = mode === 'dollar' ? curve[i] : ((curve[i] - initialCapital) / initialCapital) * 100
    data.push({ time, value })
  }
  // Deduplicate by time (lightweight-charts requires unique times)
  const seen = new Set<string>()
  return data.filter(d => {
    if (seen.has(d.time)) return false
    seen.add(d.time)
    return true
  })
}
