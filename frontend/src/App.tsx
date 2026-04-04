import { useState, useEffect } from 'react'
import { Routes, Route } from 'react-router-dom'
import type { CycleSummary } from './types'
import { getCycles } from './api/client'
import Layout from './components/layout/Layout'
import AssetTabs from './components/shared/AssetTabs'
import OverviewPage from './pages/OverviewPage'
import AssetPage from './pages/AssetPage'
import StrategyDetailPage from './pages/StrategyDetailPage'

export default function App() {
  const [cycle, setCycle] = useState<CycleSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)

  useEffect(() => {
    getCycles()
      .then(cycles => { if (cycles.length > 0) setCycle(cycles[0]) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  return (
    <Layout>
      {!loading && <AssetTabs cycle={cycle} />}
      <Routes>
        <Route path="/" element={
          <OverviewPage cycle={cycle} setCycle={setCycle} running={running} setRunning={setRunning} />
        } />
        <Route path="/asset/:instrument" element={<AssetPage cycle={cycle} />} />
        <Route path="/strategy/:id" element={<StrategyDetailPage />} />
      </Routes>
    </Layout>
  )
}
