# StrategyLab

**AI-powered trading strategy research platform for prop firm traders.** Generates, backtests, ranks, and displays day trading strategies with intelligence-first market analysis, 2-year historical validation, and prop firm compliance checking.

Built for futures micro contracts (MES, MNQ, MYM, MGC, MCL) targeting Topstep, Apex, and Funded Hive evaluations.

![Python](https://img.shields.io/badge/Python-3.12+-blue) ![React](https://img.shields.io/badge/React-19-61DAFB) ![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6) ![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688) ![TailwindCSS](https://img.shields.io/badge/Tailwind-3-38B2AC)

---

## What It Does

StrategyLab is a full-stack trading research system that:

1. **Scouts** each asset's current market regime using TradingView MCP (trending, ranging, volatile)
2. **Generates** 150 regime-tuned strategies per asset (not random — weighted toward what works)
3. **Backtests** every strategy at 0.25% and 0.5% risk on 2 years of 15-minute data
4. **Validates** with 18-month in-sample / 6-month out-of-sample split to catch overfitting
5. **Ranks** using weighted scoring with penalties for non-compliance, instability, and outlier dependence
6. **Simulates** prop firm evaluation pass probability via Monte Carlo (1,000+ simulations)
7. **Optimizes** portfolios of 2-3 uncorrelated strategies to minimize combined drawdown
8. **Displays** everything in a premium dark-mode dashboard with per-asset tabs and TradingView charts

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (React + TypeScript + Tailwind)                   │
│  ├─ Overview Page (global stats, per-asset cards)           │
│  ├─ Asset Pages (chart carousel, ranked table, filters)     │
│  └─ Strategy Detail (IS/OOS comparison, equity curves)      │
├─────────────────────────────────────────────────────────────┤
│  REST API (FastAPI)                                         │
│  POST /api/cycles/run → full pipeline                       │
│  GET  /api/cycles, /api/strategies/:id                      │
├─────────────────────────────────────────────────────────────┤
│  Engine Layer (Python)                                      │
│  ├─ Scout (TradingView MCP → regime classification)         │
│  ├─ Generator (150 strategies/asset, regime-weighted)       │
│  ├─ Backtester (bar-by-bar, 16 indicators, 24 triggers)    │
│  ├─ Ranker (weighted scoring + OOS penalties)               │
│  ├─ Monte Carlo Eval (prop firm pass probability)           │
│  ├─ Portfolio Optimizer (min DD across 2-3 strategies)      │
│  ├─ ORB Research (15 documented variations)                 │
│  ├─ VWAP Reversion + Session Rotation engines               │
│  ├─ Hedge Simulator (cross-account modeling)                │
│  └─ Pine Script Converter (export to TradingView)           │
├─────────────────────────────────────────────────────────────┤
│  Data Layer                                                 │
│  ├─ Twelve Data API (15m candles, 2-year paginated fetch)   │
│  ├─ SQLite (cycles, strategies, results, candle cache)      │
│  └─ TradingView MCP (market intelligence)                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Features

### Strategy Generation
- **1,000-strategy catalog** across 20 families (RSI, MACD, Bollinger, EMA, Stochastic, Donchian, Keltner, Ichimoku, VWAP, CCI, Williams%R, ROC, ADX, OBV, and more)
- **Regime-aware generation** — scouts market conditions first, then weights strategy types accordingly
- **15 ORB variations** — Classic, Crabel Stretch, NR7, NR4/Inside Day, Fisher ACD, VWAP Confirm, Volume Spike, Retest, Gap Filter, Fade, Trend Filter, EMA Filter, Trailing, Multi-TF, Prev Day H/L
- **Structural edge strategies** — ORB, VWAP mean reversion, session rotation with daily loss circuit breaker

### Backtesting
- **16 technical indicators** computed on numpy arrays
- **24 entry triggers** with 7 confirmation filters
- **Bar-by-bar simulation** with slippage, commission, and position sizing
- **2-year historical data** via Twelve Data API with SQLite caching
- **18mo/6mo IS/OOS validation** — catches overfitting before you trade it

### Prop Firm Compliance
- **4% max drawdown** for futures (Topstep, Apex)
- **8% max drawdown** for CFDs (Funded Hive, FTMO)
- **Monte Carlo evaluation simulator** — estimates probability of passing Topstep 50K, 100K, or Apex 50K
- **Monte Carlo WR x R:R matrix** — shows pass probability for every win rate / risk-reward combination
- **Funded phase income projection** — expected monthly income once funded

### Portfolio Optimization
- Finds optimal 2-3 strategy combinations that minimize combined drawdown
- Pearson correlation analysis between strategy equity curves
- Diversification scoring (different types, instruments, sessions)

### Cross-Account Hedge Modeling
- Simulates opposite positions across futures and CFD prop firm accounts
- Trade-based model (discrete trades, not price drift)
- Sticky trailing drawdown (matches real prop firm rules)
- Scaling model from initial pairs to 12-month compound growth
- Full economics: challenge costs, payout splits, ROI per attempt

### Pine Script Export
- Converts any strategy to TradingView Pine Script v5
- Handles all 24 triggers, 15+ indicators, ORB strategies
- Copy-paste into TradingView's Pine Editor

### Dashboard
- **Dark mode** premium trading UI
- **Per-asset tabs** — MES, MNQ, MYM, MGC, MCL
- **TradingView lightweight-charts** for equity curves and drawdowns
- **Chart carousel** — cycle through top 10 strategies per asset with $/% toggle
- **IS/OOS comparison** — side-by-side in-sample vs out-of-sample metrics
- **Overfit detection** — automatic warning when OOS significantly underperforms IS
- **Filters** — search, strategy type (8 types), compliance, risk view, sort

---

## Quick Start

### Prerequisites
- Python 3.12+
- Node.js 18+
- Twelve Data API key (free tier works — [get one here](https://twelvedata.com/))

### Backend Setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Optional: install TradingView MCP for market intelligence
pip install tradingview-mcp-server

# Configure
cp .env.example .env
# Edit .env and add your TWELVEDATA_API_KEY

# Run
uvicorn app.main:app --port 8000
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` and click **Scout & Generate Strategies**.

---

## Project Structure

```
strategy-lab/
├── backend/
│   ├── app/
│   │   ├── main.py                          # FastAPI app
│   │   ├── config.py                        # Environment config
│   │   ├── models/
│   │   │   ├── market.py                    # Candle, instrument specs
│   │   │   ├── strategy.py                  # StrategyDefinition
│   │   │   ├── backtest.py                  # BacktestResult, Trade
│   │   │   └── ranking.py                   # RankedStrategy, AssetResult, CycleSummary
│   │   ├── engine/
│   │   │   ├── indicators.py                # 16 technical indicators
│   │   │   ├── signals.py                   # 24 triggers, 7 confirmations
│   │   │   ├── backtester.py                # Bar-by-bar simulation engine
│   │   │   ├── generator.py                 # Regime-aware strategy factory
│   │   │   ├── scout.py                     # TradingView MCP intelligence
│   │   │   ├── ranker.py                    # Weighted scoring + penalties
│   │   │   ├── compliance.py                # Prop firm DD limits
│   │   │   ├── metrics.py                   # Strength/weakness analysis
│   │   │   ├── orb.py                       # Opening Range Breakout engine
│   │   │   ├── orb_research.py              # 15 ORB variations research suite
│   │   │   ├── vwap_reversion.py            # VWAP mean reversion engine
│   │   │   ├── session_rotation.py          # Session-aware strategy rotation
│   │   │   ├── monte_carlo_eval.py          # Prop firm eval simulator
│   │   │   ├── monte_carlo_matrix.py        # WR x R:R pass probability grid
│   │   │   ├── portfolio.py                 # Portfolio optimizer
│   │   │   ├── hedge_simulator.py           # Cross-account hedge (price-drift)
│   │   │   ├── hedge_trade_model.py         # Cross-account hedge (trade-based)
│   │   │   ├── pine_converter.py            # Strategy → Pine Script v5
│   │   │   └── strategy_catalog.py          # 1,000 well-known strategies
│   │   ├── data/
│   │   │   ├── twelvedata.py                # API client + 2Y paginated fetch + cache
│   │   │   ├── mock_data.py                 # Synthetic OHLCV generator
│   │   │   └── storage.py                   # SQLite persistence
│   │   └── api/
│   │       ├── cycles.py                    # Cycle endpoints (run, list, get)
│   │       └── strategies.py                # Strategy endpoints (detail, equity)
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.tsx                          # Routing
│   │   ├── types/index.ts                   # All TypeScript interfaces
│   │   ├── api/client.ts                    # API client
│   │   ├── pages/
│   │   │   ├── OverviewPage.tsx             # Global dashboard
│   │   │   ├── AssetPage.tsx                # Per-asset view
│   │   │   └── StrategyDetailPage.tsx       # Full strategy detail
│   │   └── components/
│   │       ├── layout/Layout.tsx            # Dark mode chrome
│   │       ├── charts/LightweightChart.tsx  # TradingView charts
│   │       ├── strategies/                  # Table, carousel, comparison, charts
│   │       ├── filters/FilterBar.tsx        # Search, type, compliance, sort
│   │       └── shared/                      # Badge, pagination, metrics
│   ├── package.json
│   └── tailwind.config.js
└── .mcp.json                                # TradingView MCP config
```

---

## Instruments

| Code | Name | Twelve Data Symbol | Market |
|---|---|---|---|
| MES | S&P 500 Micro | SPY (ETF proxy) | Futures |
| MNQ | Nasdaq 100 Micro | QQQ (ETF proxy) | Futures |
| MYM | Dow Jones Micro | DIA (ETF proxy) | Futures |
| MGC | Gold Micro | GLD (ETF proxy) | Futures |
| MCL | Crude Oil Micro | USO (ETF proxy) | Futures |

*Uses ETF proxies on the Twelve Data free tier. Real futures symbols available via TradingView Desktop bridge.*

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/cycles/run` | Run a full cycle: scout → generate → backtest → rank |
| GET | `/api/cycles` | List all completed cycles |
| GET | `/api/cycles/:id` | Get cycle with per-asset results |
| GET | `/api/strategies/:id` | Full strategy detail + both risk-level results |
| GET | `/api/strategies/:id/equity` | Equity and drawdown curve data |
| GET | `/api/health` | Health check |

---

## Research Results

### ORB (Opening Range Breakout) — 15 Variations, 2 Years, 3 Timeframes

Tested 1,350+ backtests across all variations, timeframes, and assets:

- **1-hour is the best timeframe** for ORB (9.7% profitable+compliant vs 2.9% on 15m)
- **Gold (MGC) and Crude (MCL)** are the only consistently profitable ORB assets
- **NR4/Inside Day** has the highest hit rate (40% of configs profitable)
- **Retest entry** produces the most trades with meaningful edge (231 trades, PF 1.16)
- **Best single result:** Retest on MGC, 1h, +$3,994 over 2 years (+4%/yr), 3.66% max DD
- **MACD and Crabel Stretch** don't work on any asset or timeframe

### TradingView Baseline (6 Strategies, 5 Assets, 2 Years)

- EMA Cross dominates indices and gold (+84% on GLD)
- Bollinger Mean Reversion has tightest drawdowns
- MACD Crossover loses on 4/5 assets
- Walk-forward validation caught 2 overfits (QQQ Supertrend, USO Bollinger)

### Monte Carlo Matrix

At $500 risk/trade, 3 trades/day on Topstep 50K:

| Win Rate | 2:1 R:R | 3:1 R:R |
|---|---|---|
| 45% | 51% pass | 65% pass |
| 50% | 66% pass | 71% pass |
| 55% | 77% pass | 81% pass |
| 60% | 85% pass | 85% pass |

---

## Tech Stack

**Backend:** Python 3.12+, FastAPI, NumPy, SQLite, httpx, python-dotenv

**Frontend:** React 19, TypeScript 5, Tailwind CSS 3, TradingView lightweight-charts, Lucide icons, React Router

**Data:** Twelve Data API (15m OHLCV), TradingView MCP (market intelligence)

**Charting:** TradingView lightweight-charts (open source)

---

## Configuration

Copy `.env.example` to `.env` in the backend directory:

```env
TWELVEDATA_API_KEY=your_api_key_here
DATABASE_PATH=strategylab.db
INITIAL_CAPITAL=50000
DEFAULT_TIMEFRAME=15min
```

### TradingView MCP (optional)

The `.mcp.json` in the project root configures the TradingView market intelligence server. This enables the scout engine to analyze market regime, sentiment, and strategy family performance before generating strategies.

---

## Prop Firm Compliance

| Rule | Futures | CFD |
|---|---|---|
| Max Trailing Drawdown | 4% ($2,000 on $50K) | 8% ($4,000 on $50K) |
| Daily Loss Limit | 2% ($1,000 on $50K) | Varies by firm |
| Profit Target | 6% ($3,000 on $50K) | 10% ($5,000 on $50K) |

Strategies exceeding drawdown limits are marked non-compliant and receive -40 point penalty in ranking.

---

## Disclaimer

This software is for **educational and research purposes only**. It does not constitute financial advice. Past performance does not guarantee future results. Trading futures and CFDs involves substantial risk of loss. Always do your own research and consult a qualified financial advisor before trading.

This project does not include:
- Trade execution capabilities
- Detection avoidance or concealment logic
- Rule evasion or multi-account circumvention
- "Near risk free" exploitation systems

---

## License

MIT

---

## Credits

Built with [Claude Code](https://claude.ai/code) by Anthropic.

Market data provided by [Twelve Data](https://twelvedata.com/).

Market intelligence via [TradingView MCP](https://github.com/atilaahmettaner/tradingview-mcp).

Charts powered by [TradingView Lightweight Charts](https://github.com/nicenumber/lightweight-charts).
