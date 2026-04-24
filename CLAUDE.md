# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Contains

Two independent projects share this repo:

1. **StrategyLab** (`backend/` + `frontend/`) — AI-powered trading strategy research platform for prop firm traders targeting Topstep/Apex/Funded Hive challenges on futures micro contracts (MES, MNQ, MYM, MGC, MCL).

2. **autoresearch** (`autoresearch/`) — Karpathy's autonomous LLM research framework. The agent edits `train.py`; `prepare.py` is fixed; `program.md` instructs the agent. Requires an NVIDIA GPU.

---

## StrategyLab — Commands

### Backend

```bash
cd backend
source .venv/bin/activate   # or: python3 -m venv .venv && pip install -r requirements.txt

# Run the API server
uvicorn app.main:app --port 8000 --reload

# Run all tests
pytest

# Run a single test file
pytest tests/test_topstep_rules.py

# Run a single test
pytest tests/test_topstep_rules.py::test_mll_trails_highest_end_of_day_balance_and_never_moves_down
```

### Frontend

```bash
cd frontend
npm install
npm run dev       # dev server at http://localhost:5173
npm run build     # tsc + vite build
npm run lint      # eslint
```

### Configuration

Copy `backend/.env.example` to `backend/.env`. Required var:
```
TWELVEDATA_API_KEY=your_key
```

Key optional vars controlling research scope:
- `PROP_PROFILE` — `prop_done_right_tdg` (default, MYM-only) or `broad_research` (all assets)
- `PROP_ALLOWED_SYMBOLS` / `PROP_BLOCKED_SYMBOLS` — instrument allowlist/blocklist
- `PROP_ALLOW_ETF_PROXY_DATA` — set `true` to allow ETF proxies in challenge profile
- `INITIAL_CAPITAL`, `DATABASE_PATH`, `DEFAULT_TIMEFRAME`

---

## StrategyLab — Architecture

### Pipeline (triggered by `POST /api/cycles/run`)

```
Scout (TradingView MCP → regime per asset)
  → Generator (150 regime-weighted strategies per asset)
    → Backtester (bar-by-bar, 18mo IS + 6mo OOS split)
      → Compliance check (4% DD futures / 8% CFD)
        → Ranker (weighted score + OOS penalties)
          → Monte Carlo eval (prop firm pass probability)
            → Portfolio optimizer (min combined DD, 2-3 strategies)
```

### Backend (`backend/app/`)

- **`main.py`** — FastAPI app with CORS; mounts `/api` routes
- **`config.py`** — All env-based constants (risk levels, DD thresholds, split ratios, commission model)
- **`models/`** — Pydantic models: `Candle`, `StrategyDefinition`, `BacktestResult`/`Trade`, `RankedStrategy`/`CycleSummary`
- **`engine/`** — Core computation:
  - `indicators.py` — 16 technical indicators on numpy arrays
  - `signals.py` — 24 entry triggers, 7 confirmation filters
  - `backtester.py` — bar-by-bar simulation with slippage/commission; uses `prop_risk_sizing.py` to size micro contracts under the Prop Done Right model
  - `generator.py` — regime-aware strategy factory
  - `scout.py` — TradingView MCP market intelligence
  - `ranker.py` — weighted scoring with penalties
  - `compliance.py` — drawdown limit enforcement
  - `orb.py` / `orb_research.py` — 15 Opening Range Breakout variations
  - `vwap_reversion.py`, `session_rotation.py` — structural edge strategies
  - `monte_carlo_eval.py` / `monte_carlo_matrix.py` — prop eval simulators
  - `portfolio.py` — Pearson correlation + min-DD optimizer
  - `hedge_simulator.py` / `hedge_trade_model.py` — cross-account hedge modeling
  - `pine_converter.py` — Strategy → TradingView Pine Script v5
  - `prop_done_right.py` — Jared's operating rules (MYM-only, DRB sizing, power quitting levels)
  - `prop_profile.py` — instrument selection by challenge vs. broad research profile
  - `prop_risk_sizing.py` — integer micro-contract sizing against DRB
  - `topstep_rules.py` — Topstep MLL trailing drawdown + consistency rule logic
- **`data/`**:
  - `twelvedata.py` — paginated 2-year 15m candle fetch with SQLite cache
  - `mock_data.py` — synthetic OHLCV generator for offline use
  - `storage.py` — SQLite persistence (cycles, strategies, candle cache)
- **`api/`**: `cycles.py` (run/list/get), `strategies.py` (detail + equity curves)

### Frontend (`frontend/src/`)

- **`App.tsx`** — React Router routes to Overview, Asset, and Strategy Detail pages
- **`types/index.ts`** — all TypeScript interfaces (single source of truth)
- **`api/client.ts`** — typed API client
- **`pages/`** — `OverviewPage`, `AssetPage` (per-asset tab), `StrategyDetailPage`
- **`components/strategies/`** — `StrategyTable`, `StrategyChartCarousel`, `ComparisonPanel` (IS/OOS), equity/drawdown charts
- **`components/charts/LightweightChart.tsx`** — TradingView lightweight-charts wrapper

### Prop Risk Model

Risk in the engine is sized as **Daily Risk Budget (DRB) multiples**, not account percentage. The DRB is 10% of the effective drawdown (`min(configured_dd, official_mll)`). Config `PROP_RISK_MULTIPLES=0.25,0.5` means each strategy is tested at 25% and 50% of DRB per trade. See `prop_done_right.py` and `prop_risk_sizing.py`.

The `prop_done_right_tdg` profile enforces MYM-only trading and blocks MNQ/NQ/ES/YM/RTY.

---

## autoresearch — Commands

```bash
cd autoresearch
uv sync                  # install deps (requires uv)
uv run prepare.py        # one-time data download + tokenizer (~2 min)
uv run train.py          # single 5-minute training experiment
```

The agent modifies `train.py` only. `prepare.py` is never modified. `program.md` is the agent's instruction file (human-maintained).
