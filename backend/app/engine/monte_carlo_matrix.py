"""
Monte Carlo Prop Firm Evaluation Matrix.

Unlike monte_carlo_eval.py (which resamples historical trades), this module
takes a strategy's known WIN RATE and RISK:REWARD RATIO as inputs and
simulates discrete binary trades to determine the probability of passing
a prop firm challenge.

Produces a full WR x R:R matrix showing pass rates, blow rates, and EV.
"""
from __future__ import annotations

import numpy as np


# ═══════════════════════════════════════════════════════════════════════════════
# PRESETS
# ═══════════════════════════════════════════════════════════════════════════════

TOPSTEP_50K = {
    "account_size": 50_000,
    "profit_target": 3_000,
    "max_dd": 2_000,
    "daily_limit": 1_000,
}

CFD_50K = {
    "account_size": 50_000,
    "profit_target": 5_000,
    "max_dd": 3_000,
    "daily_limit": 0,
}


# ═══════════════════════════════════════════════════════════════════════════════
# CORE SIMULATION — from Win Rate & Risk:Reward
# ═══════════════════════════════════════════════════════════════════════════════

def simulate_from_wr_rr(
    win_rate: float,
    risk_reward: float,
    risk_per_trade: float,
    trades_per_day: int,
    config: dict,
    n_sims: int = 5_000,
    max_days: int = 30,
    seed: int = 42,
) -> dict:
    """
    Simulate prop firm evaluation from a strategy's win rate and R:R ratio.

    Each trade is a coin flip:
      - Win  (probability = win_rate):  profit = risk_per_trade * risk_reward
      - Lose (probability = 1 - win_rate): loss = risk_per_trade

    Tracks trailing drawdown, daily loss, and profit target to determine
    pass/blow/timeout for each simulation.

    Returns dict with pass_rate, blow_rate, daily_blow_rate, timeout_rate,
    avg_days_to_pass, avg_profit_if_pass, p95_max_drawdown, expected_value.
    """
    profit_target = config["profit_target"]
    max_dd = config["max_dd"]
    daily_limit = config["daily_limit"]

    rng = np.random.default_rng(seed)
    total_trades = trades_per_day * max_days

    win_pnl = risk_per_trade * risk_reward
    lose_pnl = risk_per_trade

    passes = 0
    blows = 0
    daily_blows = 0
    timeouts = 0
    days_to_pass: list[int] = []
    profit_if_pass: list[float] = []
    max_drawdowns: list[float] = []

    for _ in range(n_sims):
        # Generate all trade outcomes at once: True = win, False = lose
        outcomes = rng.random(total_trades) < win_rate

        running_pnl = 0.0
        peak_pnl = 0.0
        sim_max_dd = 0.0
        outcome = "timeout"
        outcome_day = max_days

        for day in range(max_days):
            start = day * trades_per_day
            end = start + trades_per_day
            day_pnl = 0.0

            for t in range(start, end):
                if outcomes[t]:
                    running_pnl += win_pnl
                    day_pnl += win_pnl
                else:
                    running_pnl -= lose_pnl
                    day_pnl -= lose_pnl

                if running_pnl > peak_pnl:
                    peak_pnl = running_pnl

                trailing_dd = peak_pnl - running_pnl
                if trailing_dd > sim_max_dd:
                    sim_max_dd = trailing_dd

                # Check trailing drawdown limit
                if trailing_dd >= max_dd:
                    outcome = "blown_trailing"
                    outcome_day = day + 1
                    break

            if outcome == "blown_trailing":
                break

            # Check daily loss limit (0 means no limit)
            if daily_limit > 0 and day_pnl <= -daily_limit:
                outcome = "blown_daily"
                outcome_day = day + 1
                break

            # Check pass condition
            if running_pnl >= profit_target:
                outcome = "pass"
                outcome_day = day + 1
                break

        max_drawdowns.append(sim_max_dd)

        if outcome == "pass":
            passes += 1
            days_to_pass.append(outcome_day)
            profit_if_pass.append(running_pnl)
        elif outcome == "blown_trailing":
            blows += 1
        elif outcome == "blown_daily":
            daily_blows += 1
            blows += 1
        else:
            timeouts += 1

    pass_rate = passes / n_sims
    blow_rate = blows / n_sims
    daily_blow_rate = daily_blows / n_sims
    timeout_rate = timeouts / n_sims

    avg_days = float(np.mean(days_to_pass)) if days_to_pass else float(max_days)
    avg_profit = float(np.mean(profit_if_pass)) if profit_if_pass else 0.0

    max_drawdowns.sort()
    p95_idx = min(int(n_sims * 0.95), n_sims - 1)
    p95_dd = max_drawdowns[p95_idx]

    # Expected value: P(pass) * avg_profit - P(blow|timeout) * max_dd
    # This is the probability-weighted expected P&L of attempting the challenge
    ev = pass_rate * avg_profit - (blow_rate + timeout_rate) * max_dd

    return {
        "pass_rate": pass_rate,
        "blow_rate": blow_rate,
        "daily_blow_rate": daily_blow_rate,
        "timeout_rate": timeout_rate,
        "avg_days_to_pass": avg_days,
        "avg_profit_if_pass": avg_profit,
        "p95_max_drawdown": p95_dd,
        "expected_value": ev,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# FULL MATRIX — Win Rate x R:R Grid
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_WIN_RATES = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]
DEFAULT_RR_RATIOS = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]


def generate_matrix(
    config: dict,
    risk_per_trade: float,
    trades_per_day: int,
    n_sims: int = 2_000,
    max_days: int = 30,
    win_rates: list[float] | None = None,
    rr_ratios: list[float] | None = None,
) -> dict:
    """
    Generate a full WR x R:R matrix of pass rates.

    Each cell contains the full simulation result from simulate_from_wr_rr.

    Returns:
        dict with keys: rows (win rates), columns (R:R ratios),
        cells (2D list of result dicts), config, params.
    """
    if win_rates is None:
        win_rates = DEFAULT_WIN_RATES
    if rr_ratios is None:
        rr_ratios = DEFAULT_RR_RATIOS

    cells: list[list[dict]] = []
    seed = 42

    for wr in win_rates:
        row: list[dict] = []
        for rr in rr_ratios:
            result = simulate_from_wr_rr(
                win_rate=wr,
                risk_reward=rr,
                risk_per_trade=risk_per_trade,
                trades_per_day=trades_per_day,
                config=config,
                n_sims=n_sims,
                max_days=max_days,
                seed=seed,
            )
            row.append(result)
            seed += 1  # different seed per cell for independence
        cells.append(row)

    return {
        "rows": win_rates,
        "columns": rr_ratios,
        "cells": cells,
        "config": config,
        "params": {
            "risk_per_trade": risk_per_trade,
            "trades_per_day": trades_per_day,
            "n_sims": n_sims,
            "max_days": max_days,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# HEDGE MATRIX — Dual-Account Simulation
# ═══════════════════════════════════════════════════════════════════════════════

def generate_hedge_matrix(
    futures_config: dict,
    cfd_config: dict,
    risk_per_trade: float,
    trades_per_day: int,
    n_sims: int = 2_000,
    max_days: int = 30,
    win_rates: list[float] | None = None,
    rr_ratios: list[float] | None = None,
) -> dict:
    """
    Generate a WR x R:R matrix for the HEDGE scenario (two opposed accounts).

    For each WR/RR combo, simulates BOTH accounts simultaneously:
      - Futures (long): wins when strategy wins
      - CFD (short): wins when strategy loses (inverted)

    One side profits while the other draws down. The cell value is
    P(at least one account passes before both blow out).

    Returns dict with rows, columns, cells, and both configs.
    """
    if win_rates is None:
        win_rates = DEFAULT_WIN_RATES
    if rr_ratios is None:
        rr_ratios = DEFAULT_RR_RATIOS

    cells: list[list[dict]] = []
    seed = 42

    for wr in win_rates:
        row: list[dict] = []
        for rr in rr_ratios:
            result = _simulate_hedge_from_wr_rr(
                win_rate=wr,
                risk_reward=rr,
                risk_per_trade=risk_per_trade,
                trades_per_day=trades_per_day,
                futures_config=futures_config,
                cfd_config=cfd_config,
                n_sims=n_sims,
                max_days=max_days,
                seed=seed,
            )
            row.append(result)
            seed += 1
        cells.append(row)

    return {
        "rows": win_rates,
        "columns": rr_ratios,
        "cells": cells,
        "futures_config": futures_config,
        "cfd_config": cfd_config,
        "params": {
            "risk_per_trade": risk_per_trade,
            "trades_per_day": trades_per_day,
            "n_sims": n_sims,
            "max_days": max_days,
        },
    }


def _simulate_hedge_from_wr_rr(
    win_rate: float,
    risk_reward: float,
    risk_per_trade: float,
    trades_per_day: int,
    futures_config: dict,
    cfd_config: dict,
    n_sims: int,
    max_days: int,
    seed: int,
) -> dict:
    """
    Simulate hedge scenario: two opposed accounts, same trade stream.

    When strategy wins a trade:
      - Futures account gains risk_per_trade * risk_reward
      - CFD account loses risk_per_trade
    When strategy loses:
      - Futures account loses risk_per_trade
      - CFD account gains risk_per_trade * risk_reward

    Tracks both accounts independently with their own DD limits and targets.
    """
    f_target = futures_config["profit_target"]
    f_max_dd = futures_config["max_dd"]
    f_daily_limit = futures_config["daily_limit"]

    c_target = cfd_config["profit_target"]
    c_max_dd = cfd_config["max_dd"]
    c_daily_limit = cfd_config["daily_limit"]

    rng = np.random.default_rng(seed)
    total_trades = trades_per_day * max_days

    win_pnl = risk_per_trade * risk_reward
    lose_pnl = risk_per_trade

    futures_passes = 0
    cfd_passes = 0
    both_blown = 0
    timeouts = 0
    days_to_resolve: list[int] = []

    for _ in range(n_sims):
        outcomes = rng.random(total_trades) < win_rate

        f_pnl = 0.0
        f_peak = 0.0
        f_blown = False
        f_passed = False

        c_pnl = 0.0
        c_peak = 0.0
        c_blown = False
        c_passed = False

        resolved = False
        resolve_day = max_days

        for day in range(max_days):
            start = day * trades_per_day
            end = start + trades_per_day
            f_day_pnl = 0.0
            c_day_pnl = 0.0

            for t in range(start, end):
                if outcomes[t]:
                    # Strategy wins: futures gains, CFD loses
                    f_trade = win_pnl if not f_blown else 0.0
                    c_trade = -lose_pnl if not c_blown else 0.0
                else:
                    # Strategy loses: futures loses, CFD gains
                    f_trade = -lose_pnl if not f_blown else 0.0
                    c_trade = win_pnl if not c_blown else 0.0

                f_pnl += f_trade
                c_pnl += c_trade
                f_day_pnl += f_trade
                c_day_pnl += c_trade

                # Update peaks
                if not f_blown and f_pnl > f_peak:
                    f_peak = f_pnl
                if not c_blown and c_pnl > c_peak:
                    c_peak = c_pnl

                # Trailing DD checks
                if not f_blown and (f_peak - f_pnl) >= f_max_dd:
                    f_blown = True
                if not c_blown and (c_peak - c_pnl) >= c_max_dd:
                    c_blown = True

                # Pass checks
                if not f_blown and f_pnl >= f_target:
                    f_passed = True
                if not c_blown and c_pnl >= c_target:
                    c_passed = True

                # Early exit: someone passed or both blown
                if f_passed or c_passed or (f_blown and c_blown):
                    resolved = True
                    resolve_day = day + 1
                    break

            if resolved:
                break

            # Daily loss checks
            if not f_blown and f_daily_limit > 0 and f_day_pnl <= -f_daily_limit:
                f_blown = True
            if not c_blown and c_daily_limit > 0 and c_day_pnl <= -c_daily_limit:
                c_blown = True

            if f_blown and c_blown:
                resolve_day = day + 1
                break

        days_to_resolve.append(resolve_day)

        if f_passed:
            futures_passes += 1
        elif c_passed:
            cfd_passes += 1
        elif f_blown and c_blown:
            both_blown += 1
        else:
            timeouts += 1

    either_pass_rate = (futures_passes + cfd_passes) / n_sims

    return {
        "futures_pass_rate": futures_passes / n_sims,
        "cfd_pass_rate": cfd_passes / n_sims,
        "either_pass_rate": either_pass_rate,
        "both_blown_rate": both_blown / n_sims,
        "timeout_rate": timeouts / n_sims,
        "avg_days_to_resolve": float(np.mean(days_to_resolve)),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PRETTY PRINT
# ═══════════════════════════════════════════════════════════════════════════════

def print_matrix(matrix: dict) -> None:
    """Pretty-print a WR x R:R matrix as a formatted table."""
    rows = matrix["rows"]
    cols = matrix["columns"]
    cells = matrix["cells"]
    config = matrix.get("config")
    params = matrix.get("params", {})

    is_hedge = "futures_config" in matrix

    # Header
    print()
    if is_hedge:
        print("=" * 80)
        print("  HEDGE MATRIX — P(at least one account passes)")
        f_cfg = matrix["futures_config"]
        c_cfg = matrix["cfd_config"]
        print(f"  Futures: target=${f_cfg['profit_target']:,}  DD=${f_cfg['max_dd']:,}  daily=${f_cfg['daily_limit']:,}")
        print(f"  CFD:     target=${c_cfg['profit_target']:,}  DD=${c_cfg['max_dd']:,}  daily=${c_cfg['daily_limit']:,}")
    else:
        print("=" * 80)
        print("  PASS RATE MATRIX — P(passing prop firm challenge)")
        if config:
            print(f"  Target=${config['profit_target']:,}  Max DD=${config['max_dd']:,}  Daily limit=${config['daily_limit']:,}")

    print(f"  Risk/trade=${params.get('risk_per_trade', '?'):,}  Trades/day={params.get('trades_per_day', '?')}  "
          f"Sims={params.get('n_sims', '?'):,}  Max days={params.get('max_days', 30)}")
    print("=" * 80)

    # Column headers
    header = f"  {'WR':>5} |"
    for rr in cols:
        header += f" {rr:.1f}R  |"
    print(header)
    print("  " + "-" * (len(header) - 2))

    # Data rows
    for i, wr in enumerate(rows):
        line = f"  {wr*100:4.0f}% |"
        for j, rr in enumerate(cols):
            cell = cells[i][j]
            if is_hedge:
                val = cell["either_pass_rate"] * 100
            else:
                val = cell["pass_rate"] * 100

            # Color coding via symbols
            if val >= 70:
                marker = "***"
            elif val >= 50:
                marker = "** "
            elif val >= 30:
                marker = "*  "
            else:
                marker = "   "

            line += f" {val:4.0f}%{marker}|"
        print(line)

    # Legend
    print()
    print("  *** = 70%+    ** = 50%+    * = 30%+")

    # Blow rate summary for non-hedge
    if not is_hedge:
        print()
        print("  BLOW RATES (trailing DD):")
        header2 = f"  {'WR':>5} |"
        for rr in cols:
            header2 += f" {rr:.1f}R  |"
        print(header2)
        print("  " + "-" * (len(header2) - 2))
        for i, wr in enumerate(rows):
            line = f"  {wr*100:4.0f}% |"
            for j in range(len(cols)):
                cell = cells[i][j]
                val = cell["blow_rate"] * 100
                line += f" {val:4.0f}%   |"
            print(line)

    print()
