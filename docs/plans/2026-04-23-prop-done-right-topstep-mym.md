# Prop Done Right Topstep MYM Challenge Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Convert StrategyLab from a broad ETF-proxy strategy screener into a Topstep/TopstepX prop-challenge research and execution-prep system centered on the Prop Done Right / TDG rules: drawdown-first risk, MYM micros only, Daily Risk Budget, slow pass horizon, and no over-leverage.

**Architecture:** Keep the research pipeline separate from execution. Strategy generation, backtesting, ranking, and Monte Carlo simulation produce approved `StrategySpec`/`TradeIntent` candidates. A broker-neutral Prop Done Right risk gate evaluates every candidate before paper/dry-run/live adapters are ever called.

**Tech Stack:** Python 3.12/FastAPI/NumPy/SQLite backend, React/TypeScript frontend, pytest for backend safety tests, TopstepX/ProjectX API only after research + paper/dry-run validation.

---

## Current repo findings

- Backend has about 7,348 Python LOC and no meaningful test suite yet; `pytest` initially reported no tests.
- Current instruments use ETF proxies: SPY for MES, QQQ for MNQ, DIA for MYM, GLD for MGC, USO for MCL.
- Current backtester sizes positions fractionally from `equity * risk_pct / price_distance`; this is not futures-realistic and violates micro-contract integer sizing.
- Current slippage/commission are percent-based; futures should use tick slippage and round-turn contract fees.
- Current compliance is static max-drawdown percentage only; Topstep MLL trails highest end-of-day balance and is monitored intraday with realized + unrealized P&L.
- Current Monte Carlo resamples closed trades and does not model Topstep consistency, TDG daily stop, Power of Quitting, integer contracts, or slow 25-session pass pacing.

---

## Task 1: Establish Prop Done Right risk policy module

**Objective:** Encode the user-level TDG operating rules as a broker-neutral risk policy with tests.

**Files:**
- Create: `backend/app/engine/prop_done_right.py`
- Create: `backend/tests/test_prop_done_right.py`

**Status:** DONE in this first pass.

**Implemented behaviors:**
- Effective drawdown = configured drawdown unless an official MLL amount is known, then use the more conservative value.
- Daily Risk Budget = 10% of effective drawdown.
- MYM-only initial phase.
- Micros only, never minis.
- MNQ and minis blocked by default.
- Stop at DRB breach.
- Hard Power of Quitting lock at +2x DRB.
- MYM position sizing floors to integer micro contracts and returns 0 when one micro exceeds risk.

**Verification:**

```bash
cd backend
./.venv/bin/python -m pytest tests/test_prop_done_right.py -q
```

Expected: `7 passed`.

---

## Task 2: Add futures-native instrument master

**Objective:** Replace ETF-proxy risk assumptions with real futures contract specs used for sizing and execution simulation.

**Files:**
- Create: `backend/app/models/futures.py`
- Create: `backend/tests/test_futures_specs.py`
- Modify later: `backend/app/models/market.py` when wiring the backtesters.

**Status:** DONE in this first pass for standalone futures specs.

**Implemented specs/helpers:**
- MYM tick size: 1 index point
- MYM tick value: $0.50
- MYM contract type: micro
- YM contract type: mini and blocked by profile
- MES/ES, MNQ/NQ, MGC/GC, MCL/CL specs for later broader research
- `get_contract_spec`, `is_micro_symbol`, `is_mini_symbol`, and `dollars_per_contract_tick_move`

**Verification:**

```bash
cd backend
./.venv/bin/python -m pytest tests/test_futures_specs.py -q
```

Expected: `5 passed`.

---

## Task 3: Add Topstep 50K Combine rules engine

**Objective:** Model official Topstep pass/fail constraints separately from stricter TDG operating rules.

**Files:**
- Create: `backend/app/engine/topstep_rules.py`
- Create: `backend/tests/test_topstep_rules.py`

**Status:** DONE in this first pass.

**Implemented rules:**
- Starting balance: 50000
- Profit target: 3000
- MLL amount: 2000 for current Topstep 50K Trading Combine docs
- MLL floor starts at 48000
- MLL trails highest end-of-day balance minus MLL amount
- MLL locks at starting balance once it reaches 50000
- Intraday current equity = start balance + realized PnL + unrealized PnL - fees
- Breach if current equity <= MLL floor
- Consistency target: best day profit / total profit must be below 50%

**Verification:**

```bash
cd backend
./.venv/bin/python -m pytest tests/test_topstep_rules.py -q
```

Expected: `6 passed`.

---

## Task 4: Add Prop Challenge backtest wrapper

**Objective:** Wrap existing backtests with a Topstep/TDG path simulator that evaluates challenge realism without rewriting all strategies first.

**Status:** DONE in this pass.

**Files:**
- Created: `backend/app/engine/prop_challenge_sim.py`
- Created: `backend/tests/test_prop_challenge_sim.py`
- No changes needed to `backend/app/models/backtest.py`.

**Implemented behavior:**
- Groups trades by Central Time futures trading day with a clean timezone fallback.
- Enforces Daily Risk Budget lockout after daily net P&L is at or below `-DRB`.
- Enforces Power of Quitting hard lock after daily net P&L is at or above `+2x DRB`.
- Enforces configurable max trades/day.
- Tracks realized Topstep MLL checks after each accepted trade and advances the trailing MLL floor at end of day.
- Tracks best day, Topstep consistency, day P&Ls, lockouts, skipped/taken trades, and MLL floor path.
- Returns `pass`, `fail_mll`, `fail_consistency`, or `timeout` with an explanatory reason.
- Keeps target-pass-session awareness in the consistency failure reason so two-day spikes are not treated as healthy passes.

**Verification:**

```bash
cd backend
./.venv/bin/python -m pytest tests/test_prop_challenge_sim.py -q
```

Expected: `6 passed`.

---

## Task 5: Make the research cycle MYM-only by profile

**Objective:** Add a profile setting so the initial pipeline only generates and ranks MYM strategies.

**Files:**
- Create: `backend/app/engine/prop_profile.py`
- Create: `backend/tests/test_prop_profile.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/api/cycles.py`

**Status:** DONE in this pass.

**Config:**

```env
PROP_PROFILE=prop_done_right_tdg
PROP_ALLOWED_SYMBOLS=MYM
PROP_BLOCKED_SYMBOLS=MNQ,NQ,ES,YM,RTY
```

**Implemented behavior:**
- Default challenge profile processes only MYM.
- Broad research mode can still process all non-blocked instruments if explicitly selected.
- Unknown profiles fail closed to challenge behavior.
- Empty selections raise `ValueError` instead of silently broadening risk.

**Verification:**

```bash
cd backend
./.venv/bin/python -m pytest tests/test_prop_profile.py -q
```

Expected: `4 passed`.

---

## Task 6: Replace percentage risk levels with dollar DRB risk levels

**Objective:** Stop using `0.25%` and `0.5%` of nominal account size as the primary risk units; use drawdown-relative dollar risk instead.

**Files:**
- Create: `backend/app/engine/prop_risk_sizing.py`
- Create: `backend/tests/test_prop_risk_sizing.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/engine/backtester.py`
- Modify: `backend/app/engine/orb.py`
- Modify: `backend/app/engine/vwap_reversion.py`
- Modify: `backend/app/engine/session_rotation.py`
- Modify: `backend/app/api/cycles.py`
- Modify: `backend/app/models/backtest.py` comments for legacy `risk_pct` naming.

**Status:** DONE in this pass.

**Implemented behavior:**
- `PROP_RISK_MULTIPLES` defaults to `0.25,0.5` and is interpreted as DRB multiples, not account percentages.
- `PROP_RISK_DOLLARS` can override with explicit dollar risk levels.
- Default Topstep/TDG config: official MLL $2,000 -> DRB $200 -> risk level 0.25 = $50 per trade.
- Shared sizing helper floors to integer futures micro contracts.
- If one micro exceeds the risk budget, the trade is skipped.
- Default indicator backtester, ORB, VWAP reversion, and session rotation all use shared integer sizing.
- Cycles pass strategy symbols into ORB/VWAP/session routing where needed.

**Verification:**

```bash
cd backend
./.venv/bin/python -m pytest tests/test_prop_risk_sizing.py -q
```

Expected: `11 passed`.

---

## Task 7: Futures-native costs and slippage

**Objective:** Replace percent slippage and percent commission with tick/contract costs.

**Files:**
- Create: `backend/app/engine/futures_costs.py`
- Create: `backend/tests/test_futures_costs.py`
- Modify backtesters to use the cost model.

**Behavior:**
- Entry slippage in ticks.
- Stop-market exit slippage in ticks.
- Take-profit limit exit slippage can be zero or configurable.
- Round-turn fees per contract.
- P&L computed using tick value and tick distance.

---

## Task 8: Ranking score for prop-challenge survival

**Objective:** Rank strategies by probability of passing safely, not by raw return.

**Files:**
- Modify: `backend/app/engine/ranker.py`
- Modify: `backend/app/models/ranking.py`
- Add tests: `backend/tests/test_prop_ranking.py`

**New ranking priorities:**
- Pass probability over 25-session horizon.
- Low MLL breach probability.
- Low DRB lockout frequency.
- Low best-day concentration.
- Enough but not excessive trade count.
- Stable OOS profit factor.
- Penalize high-volatility instruments and any non-MYM symbol in initial phase.

---

## Task 9: Add operator checklists and scorecard models

**Objective:** Make the daily discipline tools first-class data, not notes in chat.

**Files:**
- Create: `backend/app/models/operator.py`
- Create: `backend/app/api/operator.py`
- Modify: `backend/app/main.py`
- Frontend later: checklist and scorecard components.

**Data:**
- Pre-market checklist: slept, news checked, max loss accepted, no revenge state, trade plan selected.
- Post-session scorecard: P&L, rule violations, emotional capital score, notes, screenshots optional later.

---

## Task 10: Only after research/paper validation, add dry-run TradeIntent path

**Objective:** Create the bridge from approved strategies to broker-neutral intents while keeping order placement disabled by default.

**Files:**
- Create: `backend/app/execution/trade_intent.py`
- Create: `backend/app/execution/audit.py`
- Create: `backend/app/execution/broker.py`
- Create: tests under `backend/tests/execution/`

**Hard requirement:** No live order endpoint should exist until tests prove:
- dry-run never calls ProjectX `/api/Order/place`
- live mode is blocked by default
- account ID must be allowlisted
- bracket stop is required
- audit pre-write must succeed

---

## Immediate next command

Run the current first-pass tests:

```bash
cd /home/hermes/projects/strategy-lab-autoresearch-combined/backend
./.venv/bin/python -m pytest tests/test_prop_done_right.py -q
```
