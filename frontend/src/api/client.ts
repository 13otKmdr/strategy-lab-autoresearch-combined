import type { CycleSummary, StrategyDetail } from '../types';

const BASE = '/api';

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(`${BASE}${url}`);
  if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
  return res.json();
}

export async function getCycles(): Promise<CycleSummary[]> {
  return fetchJson('/cycles');
}

export async function getCycle(cycleId: string): Promise<CycleSummary> {
  return fetchJson(`/cycles/${cycleId}`);
}

export async function runCycle(): Promise<CycleSummary> {
  const res = await fetch(`${BASE}/cycles/run`, { method: 'POST' });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getStrategyDetail(strategyId: string): Promise<StrategyDetail> {
  return fetchJson(`/strategies/${strategyId}`);
}

export async function getEquityCurves(strategyId: string): Promise<Record<string, { equity_curve: number[]; drawdown_curve: number[] }>> {
  return fetchJson(`/strategies/${strategyId}/equity`);
}
